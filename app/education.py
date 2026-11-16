"""Education level / field detection from free text."""
import re

LEVEL_NAMES = {0: "Unknown", 1: "Diploma/Intermediate", 2: "Bachelor's", 3: "Master's", 4: "PhD"}

_PHD = re.compile(r"\b(ph\.?\s?d|doctorate|doctor of philosophy)\b", re.I)
_MASTERS = re.compile(
    r"\b(master'?s?|m\.?\s?sc|m\.?\s?phil|mba|m\.?\s?s\.?\s*(?:in|of|\(|computer|cs|software|data|ai|it|engineering)|"
    r"m\.?\s?e\.?\s*(?:in|\(|computer|electrical|software))",
    re.I,
)
_BACHELORS = re.compile(
    r"\b(bachelor'?s?|b\.?\s?sc|b\.?\s?s\.?\s*(?:in|of|\(|computer|cs|software|se|it|ai|data|engineering)|"
    r"bscs|bsse|bsit|bsai|bsds|bcs|bba|b\.?\s?e\.?\s*(?:in|\(|computer|electrical|software)|undergraduate)",
    re.I,
)
_DIPLOMA = re.compile(r"\b(diploma|dae|intermediate|fsc|f\.sc|a-levels?|hssc)\b", re.I)

FIELDS = {
    "computer science": ["computer science", "bscs", "bs cs", "cs", "computing"],
    "software engineering": ["software engineering", "bsse", "bs se", "se"],
    "information technology": ["information technology", "bsit", "bs it", "it"],
    "artificial intelligence": ["artificial intelligence", "bsai", "ai"],
    "data science": ["data science", "bsds"],
    "electrical engineering": ["electrical engineering", "electronics"],
}


def detect_level(text: str) -> int:
    if not text:
        return 0
    if _PHD.search(text):
        return 4
    if _MASTERS.search(text):
        return 3
    if _BACHELORS.search(text):
        return 2
    if _DIPLOMA.search(text):
        return 1
    return 0


def detect_field(text: str):
    if not text:
        return None
    t = " " + re.sub(r"[^a-z0-9]+", " ", text.lower()) + " "
    for field, aliases in FIELDS.items():
        for a in aliases:
            if f" {a} " in t:
                return field
    return None


def parse_education(text: str) -> dict:
    return {"level": detect_level(text), "field": detect_field(text), "text": (text or "").strip() or None}
