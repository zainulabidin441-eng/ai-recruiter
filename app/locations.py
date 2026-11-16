"""Pakistan location normalisation (handles ISB / Pindi / "Lahore, Punjab" etc.)."""
import re
from typing import Optional

CITIES = {
    "Islamabad": ["islamabad", "isb", "islamabad capital territory"],
    "Rawalpindi": ["rawalpindi", "pindi", "rwp"],
    "Lahore": ["lahore", "lhr"],
    "Karachi": ["karachi", "khi"],
    "Faisalabad": ["faisalabad", "lyallpur"],
    "Multan": ["multan"],
    "Peshawar": ["peshawar"],
    "Quetta": ["quetta"],
    "Hyderabad": ["hyderabad"],  # ambiguous with India -> needs Pakistan context
    "Sialkot": ["sialkot"],
    "Gujranwala": ["gujranwala"],
    "Gujrat": ["gujrat"],
    "Abbottabad": ["abbottabad"],
    "Bahawalpur": ["bahawalpur"],
    "Sargodha": ["sargodha"],
    "Sukkur": ["sukkur"],
    "Mardan": ["mardan"],
    "Wah Cantt": ["wah cantt", "wah cantonment"],
    "Attock": ["attock"],
    "Jhelum": ["jhelum"],
    "Sahiwal": ["sahiwal"],
    "Rahim Yar Khan": ["rahim yar khan"],
    "Sheikhupura": ["sheikhupura"],
    "Kasur": ["kasur"],
    "Okara": ["okara"],
    "Larkana": ["larkana"],
    "Taxila": ["taxila"],
    "Murree": ["murree"],
    "Muzaffarabad": ["muzaffarabad"],
}

NEEDS_PAKISTAN_CONTEXT = {"Hyderabad"}
PAKISTAN_WORDS = ["pakistan", "pk", "sindh", "kpk", "khyber pakhtunkhwa", "balochistan",
                  "islamic republic of pakistan"]

TWIN_CITIES = {"Islamabad": "Rawalpindi", "Rawalpindi": "Islamabad"}


def _tokens(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def normalize_location(text: Optional[str]) -> dict:
    """Return {"city": str|None, "country": "Pakistan"|None, "display": str}."""
    out = {"city": None, "country": None, "display": (text or "").strip()}
    if not text:
        return out
    t = _tokens(text)
    has_pk = any(f" {w} " in t for w in PAKISTAN_WORDS)

    best = None  # (position, city)
    for city, aliases in CITIES.items():
        if city in NEEDS_PAKISTAN_CONTEXT and not has_pk:
            continue
        for a in aliases:
            pos = t.find(f" {a} ")
            if pos != -1 and (best is None or pos < best[0]):
                best = (pos, city)
    if best:
        out["city"] = best[1]
        out["country"] = "Pakistan"
        out["display"] = f"{best[1]}, Pakistan"
    elif has_pk:
        out["country"] = "Pakistan"
        out["display"] = "Pakistan"
    return out


def find_location_in_text(text: str) -> dict:
    """Look for a Pakistani city in the header area of a CV."""
    head = "\n".join(text.splitlines()[:25])[:1500]
    return normalize_location(head)


def search_terms(city: Optional[str]) -> list:
    """Terms to feed GitHub's `location:` qualifier."""
    if not city:
        return ["pakistan"]
    terms = [city.lower()]
    for a in CITIES.get(city, []):
        if a != city.lower() and " " not in a and len(a) >= 5 and a not in terms and len(terms) < 2:
            terms.append(a)
    return terms
