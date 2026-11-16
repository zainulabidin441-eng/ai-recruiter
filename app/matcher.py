"""Deterministic, explainable matching engine.

The score is a weighted average of the dimensions the recruiter actually asked for.
Dimensions where the candidate's data is unknown (e.g. education on GitHub) are shown as
"Unknown" and left out of the average, never counted as 0% or 100%.
"""
from .education import LEVEL_NAMES
from .locations import TWIN_CITIES
from .skills import IMPLIED_LANGUAGE, RELATED, display

WEIGHTS = {"skills": 0.45, "experience": 0.25, "location": 0.20, "education": 0.10}
PARTIAL_RELATED = 0.6
PARTIAL_LANGUAGE_ONLY = 0.25


def _score_skills(profile: dict, req: dict):
    cand = set(profile.get("skills", []))
    detail, total = [], 0.0
    for s in req["skills"]:
        name = display(s)
        if s in cand:
            detail.append({"skill": name, "status": "match", "note": None})
            total += 1.0
            continue
        related = [r for r in RELATED.get(s, []) if r in cand]
        if related:
            detail.append({"skill": name, "status": "partial", "note": f"related: {display(related[0])}"})
            total += PARTIAL_RELATED
        elif IMPLIED_LANGUAGE.get(s) in cand:
            detail.append({"skill": name, "status": "partial", "note": f"knows {display(IMPLIED_LANGUAGE[s])}, no {name} evidence"})
            total += PARTIAL_LANGUAGE_ONLY
        else:
            detail.append({"skill": name, "status": "miss", "note": None})
    score = total / len(req["skills"])
    sym = {"match": "✓", "partial": "~", "miss": "✗"}
    text = " · ".join(f"{d['skill']} {sym[d['status']]}" for d in detail)
    status = "match" if score >= 0.95 else "partial" if score >= 0.4 else "miss"
    return score, status, text, detail


def _score_experience(profile: dict, req: dict):
    need = req["min_experience_years"]
    have = profile.get("experience_years")
    if have is None:
        return None, "unknown", "Not stated on this profile"
    est = profile.get("experience_source") == "github_estimate"
    label = f"~{have:g} yrs of GitHub activity (estimate)" if est else f"{have:g} yrs"
    if need == 0:
        return 1.0, "match", f"{label}; fresh graduates welcome"
    ratio = min(have / need, 1.0)
    status = "match" if have >= need else "partial" if ratio >= 0.6 else "miss"
    return ratio, status, f"{label} vs {need:g}+ required"


def _score_location(profile: dict, req: dict):
    if req.get("country_only"):
        if profile.get("country") == "Pakistan":
            return 1.0, "match", f"{profile.get('city') or 'Pakistan'}"
        return None, "unknown", "Location not stated"
    want = req["location"]
    city, country = profile.get("city"), profile.get("country")
    if city == want:
        return 1.0, "match", f"{city} (exact)"
    if city and TWIN_CITIES.get(want) == city:
        return 0.8, "partial", f"{city} (twin city of {want})"
    if city:
        return 0.3, "miss", f"{city}, not {want}"
    if country == "Pakistan":
        return 0.5, "partial", f"Pakistan (city not specified), wanted {want}"
    return None, "unknown", "Location not stated"


def _score_education(profile: dict, req: dict):
    edu = profile.get("education") or {}
    have = edu.get("level", 0)
    need = req.get("education_level", 0)
    if not have:
        src = "upload a CV to check" if profile.get("source") == "github" else "not found in CV"
        return None, "unknown", f"Unknown ({src})"
    label = LEVEL_NAMES[have] + (f" in {edu['field']}" if edu.get("field") else "")
    if have < need:
        return 0.5, "partial", f"{label}, wanted {LEVEL_NAMES[need]}"
    want_field = req.get("education_field")
    if want_field and edu.get("field") and edu["field"] != want_field:
        return 0.8, "partial", f"{label}, wanted {want_field}"
    return 1.0, "match", label


def score_candidate(profile: dict, req: dict) -> dict:
    dims = []  # (key, label, weight, score|None, status, detail)
    skills_detail = []
    if req.get("skills"):
        sc, st, text, skills_detail = _score_skills(profile, req)
        dims.append(("skills", "Skills", WEIGHTS["skills"], sc, st, text))
    if req.get("min_experience_years") is not None:
        sc, st, text = _score_experience(profile, req)
        dims.append(("experience", "Experience", WEIGHTS["experience"], sc, st, text))
    if req.get("location") or req.get("country_only"):
        sc, st, text = _score_location(profile, req)
        dims.append(("location", "Location", WEIGHTS["location"], sc, st, text))
    if req.get("education_level"):
        sc, st, text = _score_education(profile, req)
        dims.append(("education", "Education", WEIGHTS["education"], sc, st, text))

    known = [d for d in dims if d[3] is not None]
    total_w = sum(d[2] for d in known)
    overall = round(100 * sum(d[2] * d[3] for d in known) / total_w) if total_w else 0

    breakdown = []
    for key, label, w, sc, st, text in dims:
        breakdown.append({
            "key": key, "label": label, "status": st,
            "score": None if sc is None else round(sc * 100),
            "weight": round(100 * w / total_w) if (total_w and sc is not None) else 0,
            "detail": text,
        })
    return {"score": overall, "breakdown": breakdown, "skills_detail": skills_detail,
            "skills_score": next((d[3] for d in dims if d[0] == "skills"), None)}


def rank(profiles: list, req: dict) -> list:
    scored = []
    for p in profiles:
        item = dict(p)
        item["match"] = score_candidate(p, req)
        scored.append(item)

    # drop candidates with (almost) none of the required skills, unless that would leave too few
    if req.get("skills"):
        relevant = [c for c in scored if (c["match"]["skills_score"] or 0) >= 0.2]
        if len(relevant) >= 3:
            scored = relevant

    scored.sort(key=lambda c: (c["match"]["score"], c.get("followers", 0), c.get("public_repos", 0)),
                reverse=True)
    return scored
