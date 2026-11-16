"""Live candidate search on the official GitHub REST API (public data only)."""
import asyncio
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

import httpx

from . import config, database
from .locations import normalize_location, search_terms
from .skills import (GITHUB_LANGUAGES, IMPLIED_LANGUAGE, NOTEBOOK_SKILLS, canonicalize,
                     extract_skills)

API = "https://api.github.com"


class GitHubError(Exception):
    """Problems the recruiter can act on (bad token, rate limit...)."""


def _headers() -> dict:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AI-Recruiter-FYP",
    }
    if config.GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return h


def safe_url(url: Optional[str]) -> Optional[str]:
    """Only allow http(s) links (profile fields are user-controlled)."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url or " " in url:
        return None
    if not re.match(r"^https?://", url, re.I):
        if "." not in url or url.lower().startswith(("javascript:", "data:", "mailto:")):
            return None
        url = "https://" + url
    return url if re.match(r"^https?://", url, re.I) else None


async def _get(client: httpx.AsyncClient, path: str, params: Optional[dict] = None,
               cache_key: Optional[str] = None):
    if cache_key:
        cached = database.cache_get(cache_key, config.CACHE_TTL_SECONDS)
        if cached is not None:
            return cached.get("v")
    try:
        r = await client.get(API + path, params=params, headers=_headers())
    except httpx.HTTPError as e:
        raise GitHubError(f"Could not reach GitHub ({e.__class__.__name__}). Check your internet connection.")

    if r.status_code == 200:
        data = r.json()
        if cache_key:
            database.cache_set(cache_key, {"v": data})
        return data
    if r.status_code == 404:
        if cache_key:
            database.cache_set(cache_key, {"v": None})
        return None
    if r.status_code == 401:
        raise GitHubError("GitHub rejected your GITHUB_TOKEN. Create a new token and update the .env file.")
    if r.status_code in (403, 429):
        if r.headers.get("x-ratelimit-remaining") == "0" or "rate limit" in r.text.lower():
            hint = "" if config.GITHUB_TOKEN else " Add a free GITHUB_TOKEN to your .env file to raise the limit."
            raise GitHubError("GitHub API rate limit reached. Wait a few minutes and try again." + hint)
        raise GitHubError(f"GitHub refused the request (403): {r.text[:150]}")
    if r.status_code == 422:
        return None  # invalid search query; treat as no results
    raise GitHubError(f"GitHub error {r.status_code}")


# ------------------------------------------------------------------ searching
def pick_languages(skills: list) -> list:
    langs = []
    for s in skills:
        lang = s if s in GITHUB_LANGUAGES else IMPLIED_LANGUAGE.get(s)
        if lang and lang in GITHUB_LANGUAGES and lang not in langs:
            langs.append(lang)
    if "python" in langs and any(s in NOTEBOOK_SKILLS for s in skills):
        langs.append("jupyter notebook")
    return langs[:2]


def _quote(v: str) -> str:
    return f'"{v}"' if " " in v else v


def build_queries(req: dict, fallback_country: bool = False) -> list:
    terms = ["pakistan"] if fallback_country or not req.get("location") else search_terms(req["location"])
    langs = pick_languages(req.get("skills", [])) or [None]
    queries = []
    for term in terms:
        for lang in langs:
            q = f"location:{_quote(term)} repos:>=2 type:user"
            if lang:
                q += f" language:{_quote(lang)}"
            queries.append(q)
    return queries


async def _search_logins(client, queries: list, per_page: int) -> list:
    """Run the search queries and interleave results so every query contributes."""
    lists = []
    for q in queries:
        data = await _get(
            client, "/search/users",
            {"q": q, "sort": "repositories", "order": "desc", "per_page": per_page},
            cache_key=f"search:{q}:{per_page}",
        )
        lists.append([u["login"] for u in (data or {}).get("items", [])])
        await asyncio.sleep(0.3)  # be gentle with the search rate limit
    merged, seen = [], set()
    for i in range(max((len(x) for x in lists), default=0)):
        for lst in lists:
            if i < len(lst) and lst[i].lower() not in seen:
                seen.add(lst[i].lower())
                merged.append(lst[i])
    return merged


# ------------------------------------------------------------ profile building
def _years_since(iso: str) -> float:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return max((datetime.now(timezone.utc) - dt).days / 365.25, 0.0)


def make_profile(user: dict, repos: list, socials: list) -> dict:
    login = user["login"]
    own = [r for r in repos if not r.get("fork")]

    counts = Counter()
    for r in own:
        lang = (r.get("language") or "")
        if lang.lower() == "jupyter notebook":
            counts["python"] += 1
        else:
            canon = canonicalize(lang)
            if canon:
                counts[canon] += 1
        text = " ".join([
            (r.get("name") or "").replace("-", " ").replace("_", " "),
            r.get("description") or "",
            " ".join(r.get("topics") or []),
        ])
        for s in extract_skills(text):
            counts[s] += 1
    for s in extract_skills(user.get("bio") or ""):
        counts[s] += 2  # self-declared in bio
    skills = [s for s, _ in counts.most_common(15)]

    dates = [r["created_at"] for r in own if r.get("created_at")]
    first = min(dates) if dates else user.get("created_at")
    experience = round(_years_since(first), 1) if first else None
    pushed = [r["pushed_at"] for r in own if r.get("pushed_at")]
    last_active = max(pushed)[:10] if pushed else None

    top = sorted(own, key=lambda r: (r.get("stargazers_count", 0), r.get("pushed_at") or ""), reverse=True)[:3]
    top_repos = [{
        "name": r["name"], "url": safe_url(r.get("html_url")), "language": r.get("language"),
        "stars": r.get("stargazers_count", 0), "description": (r.get("description") or "")[:120],
    } for r in top]

    linkedin = None
    for acc in socials or []:
        if (acc.get("provider") or "").lower() == "linkedin":
            linkedin = safe_url(acc.get("url"))
    if not linkedin:
        blob = f"{user.get('bio') or ''} {user.get('blog') or ''}"
        m = re.search(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/[A-Za-z0-9_%-]+", blob, re.I)
        linkedin = safe_url(m.group(0)) if m else None

    loc = normalize_location(user.get("location"))
    return {
        "id": f"gh:{login.lower()}",
        "source": "github",
        "name": user.get("name") or login,
        "username": login,
        "headline": (user.get("bio") or "").strip()[:200] or None,
        "location_raw": user.get("location"),
        "city": loc["city"],
        "country": loc["country"],
        "skills": skills,
        "experience_years": experience,
        "experience_source": "github_estimate",
        "education": {"level": 0, "field": None, "text": None},
        "email": (user.get("email") or None),  # public profile e-mail only
        "github_url": safe_url(user.get("html_url")),
        "linkedin_url": linkedin,
        "website": safe_url(user.get("blog")),
        "cv_url": None,
        "avatar_url": safe_url(user.get("avatar_url")),
        "top_repos": top_repos,
        "followers": user.get("followers", 0),
        "public_repos": user.get("public_repos", 0),
        "last_active": last_active,
    }


async def _build_profile(client, login: str, sem: asyncio.Semaphore) -> Optional[dict]:
    async with sem:
        user = await _get(client, f"/users/{login}", cache_key=f"user:{login.lower()}")
        if not user:
            return None
        # skip people who are clearly not in Pakistan before spending more requests
        if normalize_location(user.get("location"))["country"] != "Pakistan":
            return None
        repos = await _get(
            client, f"/users/{login}/repos",
            {"per_page": 100, "sort": "pushed", "type": "owner"},
            cache_key=f"repos:{login.lower()}",
        ) or []
        socials = []
        if config.GITHUB_TOKEN:
            socials = await _get(client, f"/users/{login}/social_accounts",
                                 cache_key=f"social:{login.lower()}") or []
    return make_profile(user, repos, socials)


async def search_github(req: dict, limit: Optional[int] = None):
    """Returns (profiles, warnings). Raises GitHubError if nothing could be fetched."""
    limit = limit or config.MAX_GITHUB_CANDIDATES
    warnings = []
    if not config.GITHUB_TOKEN:
        limit = min(limit, 10)
        warnings.append("No GITHUB_TOKEN set, so the search is limited to ~10 profiles. "
                        "Add a free token in .env for better results.")

    async with httpx.AsyncClient(timeout=30) as client:
        logins = await _search_logins(client, build_queries(req), per_page=min(limit, 30))
        if len(logins) < max(8, limit // 3) and req.get("location"):
            extra = await _search_logins(client, build_queries(req, fallback_country=True), per_page=min(limit, 30))
            have = {x.lower() for x in logins}
            logins += [x for x in extra if x.lower() not in have]
        logins = logins[: limit * 2 if config.GITHUB_TOKEN else limit]  # extra because some get filtered out

        sem = asyncio.Semaphore(6)
        results = await asyncio.gather(*[_build_profile(client, lg, sem) for lg in logins],
                                       return_exceptions=True)

    profiles = [r for r in results if isinstance(r, dict)]
    errors = [r for r in results if isinstance(r, Exception)]
    if errors and not profiles:
        first = errors[0]
        raise first if isinstance(first, GitHubError) else GitHubError(str(first))
    if errors:
        warnings.append("GitHub rate limit was hit part-way, so some profiles were skipped.")
    return profiles[:limit], warnings
