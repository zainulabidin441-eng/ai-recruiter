"""Turns the recruiter's chat message into structured hiring requirements."""
import re
from typing import Optional

from . import llm
from .education import LEVEL_NAMES, parse_education
from .locations import normalize_location
from .skills import canonicalize, display, extract_skills

WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "fresh": 0, "fresher": 0}

ROLE_SKILLS = {
    "machine learning engineer": ["python", "machine learning"],
    "ml engineer": ["python", "machine learning"],
    "ai engineer": ["python", "machine learning"],
    "data scientist": ["python", "data science"],
    "data analyst": ["python", "data analysis"],
    "django developer": ["python", "django"],
    "flask developer": ["python", "flask"],
    "frontend developer": ["javascript", "html", "css"],
    "front end developer": ["javascript", "html", "css"],
    "react developer": ["react", "javascript"],
    "node developer": ["node.js", "javascript"],
    "flutter developer": ["flutter", "dart"],
    "android developer": ["android"],
    "ios developer": ["ios", "swift"],
    "devops engineer": ["docker", "linux"],
    "wordpress developer": ["wordpress", "php"],
    "laravel developer": ["laravel", "php"],
}

SEARCH_HINTS = re.compile(
    r"\b(developer|engineer|programmer|candidate|candidates|intern|internship|hire|hiring|looking for|"
    r"need|want|find|search|show me|recruit|experience|years?|devops|scientist|analyst|designer|"
    r"fresher|junior|senior)\b", re.I)

SYSTEM_PROMPT = """You are the requirement-extraction module of an AI recruiting assistant used by recruiters in Pakistan.
Read the recruiter's latest message and return ONLY a JSON object with exactly these keys:
{
  "intent": "search" or "chat",
  "job_role": string or null,
  "skills": [string],
  "min_experience_years": number or null,
  "location": string or null,
  "education": string or null,
  "reply": string or null
}
Rules:
- intent = "search" if the recruiter wants candidates (any role, skills, experience or city). Otherwise "chat".
- skills: technical skills/tools/frameworks only, e.g. ["Python","FastAPI","Machine Learning"]. Do not put the job title or city in skills.
- min_experience_years: a number (e.g. 3). "3 year experienced" -> 3. "fresher" -> 0. null if not mentioned.
- location: a Pakistani city name as written by the recruiter (e.g. "Islamabad", "ISB", "Pindi"), or "Pakistan". null if not mentioned.
- education: e.g. "BS Computer Science", "Masters". null if not mentioned.
- If a previous search is provided AND the new message is clearly a refinement of it (e.g. "make it Lahore", "also needs Docker", "5 years instead"), start from the previous values and apply the change. If the message is a brand new request, ignore the previous search.
- If intent is "chat": put a short, friendly reply (max 2 sentences) in "reply" that helps the recruiter, e.g. explains you can find developers in Pakistan from GitHub and uploaded CVs, and give one example request. Otherwise reply is null.
Output JSON only."""


def _to_number(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        n = float(value)
        return n if 0 <= n <= 50 else None
    except (TypeError, ValueError):
        return None


def _years_from_text(text: str) -> Optional[float]:
    t = text.lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:-\s*)?(?:years?|yrs?|yr)\b", t)
    if m:
        return float(m.group(1))
    m = re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s*\+?\s*(?:-\s*)?(?:years?|yrs?)\b", t)
    if m:
        return float(WORD_NUMBERS[m.group(1)])
    if re.search(r"\bfresh(?:er|ers)?\b|\bfresh graduate\b", t):
        return 0.0
    return None


def _education_from_text(text: str) -> Optional[str]:
    m = re.search(
        r"\b((?:bs|b\.s|bsc|bachelor'?s?|ms|m\.s|msc|master'?s?|phd|ph\.d)\b(?:\s*(?:in|of)?\s*"
        r"(?:computer science|software engineering|information technology|artificial intelligence|data science|cs|se|it|ai))?)",
        text, re.I)
    return m.group(1).strip() if m else None



_ROLE_NOUNS = r"(developers?|engineers?|programmers?|scientists?|analysts?|designers?)"
_ROLE_STOP = {"a", "an", "the", "i", "we", "want", "need", "find", "me", "show", "hire", "looking", "for",
              "with", "and", "or", "of", "in", "at", "from", "experienced", "experinced", "experience",
              "year", "years", "yr", "yrs", "senior", "junior", "good", "best", "some", "any", "please",
              "is", "are", "to", "who", "has", "have", "can", "do", "dev"}


def _guess_role(message: str) -> Optional[str]:
    """Pick the job title from phrases like '3 year experienced python developer'."""
    m = re.search(r"\b" + _ROLE_NOUNS + r"\b", message, re.I)
    if not m:
        return None
    before = re.findall(r"[A-Za-z\.\+#/]+|\d+", message[: m.start()])
    words = []
    for w in reversed(before):
        if w.lower() in _ROLE_STOP or any(ch.isdigit() for ch in w):
            break
        words.append(w)
        if len(words) == 2:
            break
    noun = m.group(1).lower().rstrip("s") if m.group(1).lower() != "analysts" else "analyst"
    title = " ".join(list(reversed(words)) + [noun]).strip()
    return title[0].upper() + title[1:] if title else None


def heuristic_parse(message: str) -> dict:
    """Rule-based fallback used when Groq is unavailable."""
    skills = extract_skills(message)
    years = _years_from_text(message)
    loc = normalize_location(message)
    edu = _education_from_text(message)
    role = _guess_role(message)
    is_search = bool(skills or years is not None or loc["city"] or (SEARCH_HINTS.search(message) and (role or loc["country"])))
    return {
        "intent": "search" if is_search else "chat",
        "job_role": role,
        "skills": [display(s) for s in skills],
        "min_experience_years": years,
        "location": loc["city"] or loc["country"],
        "education": edu,
        "reply": None if is_search else (
            "Hi! Tell me who you're looking for, for example: "
            "\"I need a Python developer in Islamabad with 3 years of experience and FastAPI\". "
            "I'll search GitHub and your uploaded CVs and rank the best matches."),
    }


def _finalize(raw: dict, message: str) -> dict:
    """Validate/normalise model output into the requirement structure used everywhere."""
    skills = []
    for s in raw.get("skills") or []:
        if not isinstance(s, str):
            continue
        canon = canonicalize(s)
        if canon and canon not in skills:
            skills.append(canon)
    # also trust skills literally present in the message
    for s in extract_skills(message):
        if s not in skills:
            skills.append(s)

    role = raw.get("job_role") if isinstance(raw.get("job_role"), str) else None
    years = _to_number(raw.get("min_experience_years"))
    if years is None:
        years = _years_from_text(message)

    loc_text = raw.get("location") if isinstance(raw.get("location"), str) else None
    loc = normalize_location(loc_text) if loc_text else {"city": None, "country": None}
    if not loc["city"] and not loc["country"]:
        loc = normalize_location(message)

    edu_text = raw.get("education") if isinstance(raw.get("education"), str) else None
    edu = parse_education(edu_text or "")
    if not edu["level"] and edu_text:
        edu = parse_education(_education_from_text(edu_text) or edu_text)

    if not skills:  # derive defaults from the role title, e.g. "ML engineer"
        probe = f"{role or ''} {message}".lower()
        for key, defaults in ROLE_SKILLS.items():
            if key in probe:
                skills = list(defaults)
                break

    req = {
        "job_role": role,
        "skills": skills,
        "min_experience_years": years,
        "location": loc["city"],
        "country_only": bool(loc["country"] and not loc["city"]),
        "education_text": edu_text,
        "education_level": edu["level"],
        "education_field": edu["field"],
    }
    req["summary"] = describe(req)
    return req


def describe(req: dict) -> str:
    parts = []
    parts.append(req.get("job_role") or "candidates")
    role_l = (req.get("job_role") or "").lower()
    extra = [display(s) for s in req.get("skills", []) if display(s).lower() not in role_l and s not in role_l]
    if extra:
        parts.append("with " + ", ".join(extra))
    if req.get("min_experience_years") is not None:
        y = req["min_experience_years"]
        exp_txt = "fresh graduate" if y == 0 else f"{y:g}+ years experience"
        parts.append(("and " if extra else "with ") + exp_txt if y != 0 else exp_txt)
    if req.get("education_level"):
        parts.append(LEVEL_NAMES[req["education_level"]] + (f" in {req['education_field']}" if req.get("education_field") else ""))
    if req.get("location"):
        parts.append(f"in {req['location']}")
    elif req.get("country_only"):
        parts.append("in Pakistan")
    return " ".join(parts)


def _inherit_previous(req: dict, previous: dict, message: str) -> dict:
    """Basic refinement without the LLM: "make it Lahore" keeps the earlier skills/experience."""
    if req["skills"] or req["job_role"]:
        return req  # looks like a brand-new request
    req["skills"] = list(previous.get("skills", []))
    req["job_role"] = previous.get("job_role")
    if req["min_experience_years"] is None:
        req["min_experience_years"] = previous.get("min_experience_years")
    if not req["education_level"]:
        for key in ("education_text", "education_level", "education_field"):
            req[key] = previous.get(key)
    if not req["location"] and not req["country_only"]:
        req["location"] = previous.get("location")
        req["country_only"] = previous.get("country_only", False)
    req["summary"] = describe(req)
    return req


def _is_search(req: dict) -> bool:
    return bool(req["skills"] or req["job_role"] or req["min_experience_years"] is not None
                or req["location"] or req["country_only"])


async def parse(message: str, previous: Optional[dict] = None) -> dict:
    """Returns {"intent": "search"|"chat", "reply": str|None, "requirements": dict|None}."""
    raw = None
    if llm.available():
        try:
            prev = ""
            if previous:
                prev_json = {
                    "job_role": previous.get("job_role"),
                    "skills": [display(s) for s in previous.get("skills", [])],
                    "min_experience_years": previous.get("min_experience_years"),
                    "location": previous.get("location"),
                    "education": previous.get("education_text"),
                }
                prev = f"Previous search: {prev_json}\n"
            raw = await llm.chat_json(SYSTEM_PROMPT, f"{prev}Recruiter message: {message}", max_tokens=500)
        except Exception:
            raw = None
    used_llm = raw is not None
    if raw is None:
        raw = heuristic_parse(message)

    intent = "search" if str(raw.get("intent", "")).lower() == "search" else "chat"
    if intent == "search":
        req = _finalize(raw, message)
        if not used_llm and previous:
            req = _inherit_previous(req, previous, message)
        if _is_search(req):
            return {"intent": "search", "reply": None, "requirements": req}
        intent = "chat"
        raw["reply"] = None

    reply = raw.get("reply") or heuristic_parse("hello")["reply"]
    return {"intent": "chat", "reply": reply, "requirements": None}
