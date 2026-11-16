"""CV understanding pipeline (computer vision + document intelligence).

    PDF / scanned CV / photo of a CV
        -> PyMuPDF text layer  (digital PDFs)
        -> OpenCV clean-up + OCR (scans, photos, image-only PDF pages)
        -> Groq LLM extraction  (falls back to rule-based extraction)
        -> structured candidate profile used by the matcher
"""
import datetime as dt
import hashlib
import re
import uuid
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from starlette.concurrency import run_in_threadpool

from . import llm
from .education import LEVEL_NAMES, detect_field, detect_level
from .github_search import safe_url
from .locations import find_location_in_text, normalize_location
from .skills import canonicalize, display, extract_skills

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
MAX_PDF_PAGES = 8

# ----------------------------------------------------------------------- OCR
_ocr_engine = None


def _get_ocr():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()
        except Exception:
            _ocr_engine = False
    return _ocr_engine or None


def _estimate_skew(gray: np.ndarray) -> float:
    """Find the tilt (within ±5°) that makes text rows sharpest."""
    small = gray
    if max(gray.shape) > 1200:
        f = 1200 / max(gray.shape)
        small = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    h, w = bw.shape
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-5.0, 5.1, 1.0):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), float(angle), 1.0)
        rot = cv2.warpAffine(bw, m, (w, h), flags=cv2.INTER_NEAREST)
        score = float(np.var(rot.sum(axis=1)))
        if score > best_score:
            best_angle, best_score = float(angle), score
    return best_angle


def preprocess(img: np.ndarray) -> np.ndarray:
    """Computer-vision clean-up before OCR.

    Keeps the image in colour (this OCR engine reads spacing better that way) and only
    applies the fixes that help: size normalisation, deskew, and contrast boost for faded scans.
    """
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    h, w = img.shape[:2]
    if w < 1000:
        s = 1400 / w
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    elif w > 3200:
        s = 3200 / w
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    angle = _estimate_skew(gray)
    if abs(angle) >= 0.5:  # straighten tilted scans / phone photos
        h, w = img.shape[:2]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        img = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if float(gray.std()) < 45:  # faded / low-contrast scan -> boost local contrast
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(l)
        img = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    return img


def ocr_image(img: np.ndarray) -> str:
    engine = _get_ocr()
    prepared = preprocess(img)
    if engine is not None:
        result, _ = engine(prepared)
        if not result:
            return ""
        return "\n".join(str(r[1]) for r in result)
    try:  # optional fallback if the user installed Tesseract instead
        import pytesseract
        return pytesseract.image_to_string(prepared)
    except Exception:
        raise RuntimeError(
            "OCR engine not available. Run: pip install rapidocr-onnxruntime")


def _pixmap_to_bgr(pix) -> np.ndarray:
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    if pix.n == 3:
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    return cv2.cvtColor(arr[:, :, 0], cv2.COLOR_GRAY2BGR)


def extract_text(path: Path) -> tuple:
    """Return (text, method) where method describes how the text was obtained."""
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("This image could not be opened. Try a clear PNG or JPG.")
        return ocr_image(img), "ocr"

    try:
        import pymupdf as fitz  # PyMuPDF (new import name)
    except ImportError:
        import fitz
    pages, used_ocr, used_text = [], False, False
    with fitz.open(str(path)) as doc:
        for i in range(min(len(doc), MAX_PDF_PAGES)):
            page = doc[i]
            text = page.get_text("text").strip()
            if len(text) < 60:  # scanned page -> render it and run OCR
                pix = page.get_pixmap(dpi=200)
                text = ocr_image(_pixmap_to_bgr(pix))
                used_ocr = True
            else:
                used_text = True
            pages.append(text)
    method = "pdf-text+ocr" if (used_ocr and used_text) else "ocr" if used_ocr else "pdf-text"
    return "\n".join(pages), method


# ------------------------------------------------------- rule-based extraction
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?92|0)[\s-]?3\d{2}[\s-]?\d{7}")
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9-]{1,39})", re.I)
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/[A-Za-z0-9_%-]+", re.I)
EXP_RE = re.compile(
    r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:professional\s+|work\s+|industry\s+|relevant\s+)?experience",
    re.I)
_NAME_SKIP = re.compile(
    r"resume|curriculum|vitae|\bcv\b|profile|objective|summary|contact|address|email|phone|"
    r"experience|education|skills|projects|developer|engineer|intern|student", re.I)


def _guess_name(text: str) -> Optional[str]:
    for line in text.splitlines()[:12]:
        line = line.strip()
        if not line or len(line) > 40 or any(ch.isdigit() for ch in line) or "@" in line:
            continue
        if _NAME_SKIP.search(line):
            continue
        if re.fullmatch(r"[A-Z][a-z]+(?:[A-Z][a-z]+){1,3}", line):  # OCR glued "AliRaza"
            line = " ".join(re.findall(r"[A-Z][a-z]+", line))
        words = line.replace(",", " ").split()
        if 2 <= len(words) <= 4 and all(re.fullmatch(r"[A-Za-z.'-]+", w) for w in words):
            return line.title() if line.isupper() else line
    return None


_HEADING = re.compile(
    r"(?:technical\s+|key\s+|core\s+)?(?:skills|experience|work experience|professional experience|projects|"
    r"certifications?|achievements|interests|languages|references|summary|profile|objective|training)\s*:?", re.I)


def _education_text(text: str) -> str:
    """Return the education section if present, else lines that mention a degree."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, l in enumerate(lines):
        if re.fullmatch(r"(?:academic\s+)?(?:education|qualifications?|academics)\s*:?", l, re.I):
            section = []
            for nxt in lines[i + 1: i + 12]:
                if _HEADING.fullmatch(nxt):
                    break
                section.append(nxt)
            return "\n".join(section)
    return "\n".join(l for l in lines if detect_level(l))


def heuristic_extract(text: str) -> dict:
    emails = EMAIL_RE.findall(text)
    gh = GITHUB_RE.search(text)
    li = LINKEDIN_RE.search(text)
    phone = PHONE_RE.search(text)
    exp = None
    nums = [float(x) for x in EXP_RE.findall(text)]
    if nums:
        exp = max(nums)
    edu_text = _education_text(text)
    return {
        "name": _guess_name(text),
        "email": emails[0] if emails else None,
        "phone": phone.group(0).strip() if phone else None,
        "github_url": f"https://github.com/{gh.group(1)}" if gh and gh.group(1).lower() not in {"features", "orgs"} else None,
        "linkedin_url": safe_url(li.group(0)) if li else None,
        "skills": extract_skills(text, tolerant=True),
        "experience_years": exp,
        "education_text": edu_text,
        "location": find_location_in_text(text),
        "certifications": [],
        "projects": [],
        "headline": None,
    }


# --------------------------------------------------------------- LLM extraction
LLM_SYSTEM = """You extract structured candidate data from the OCR/text of a CV (resume).
Return ONLY a JSON object with these keys (use null or [] when unknown, never invent data):
{
  "name": string|null,
  "email": string|null,
  "phone": string|null,
  "location": string|null,
  "headline": string|null,
  "skills": [string],
  "total_experience_years": number|null,
  "education": [{"degree": string|null, "field": string|null, "institution": string|null, "year": string|null}],
  "highest_education_level": "none"|"diploma"|"bachelors"|"masters"|"phd",
  "projects": [string],
  "certifications": [string],
  "github": string|null,
  "linkedin": string|null
}
Rules: total_experience_years = years of professional work (jobs, and internships counted at half value), computed from the dates in the work history relative to today's date given below; null if no work history is listed. Skills must be technical skills only. OCR text may contain typos; fix obvious ones."""

_LEVELS = {"none": 0, "diploma": 1, "bachelors": 2, "masters": 3, "phd": 4}


async def llm_extract(text: str) -> Optional[dict]:
    if not llm.available():
        return None
    try:
        today = dt.date.today().isoformat()
        return await llm.chat_json(LLM_SYSTEM, f"Today's date: {today}\n\nCV text:\n{text[:7000]}", max_tokens=1500)
    except Exception:
        return None


# ------------------------------------------------------------------ main entry
def _num(v) -> Optional[float]:
    try:
        n = float(v)
        return round(n, 1) if 0 <= n <= 50 else None
    except (TypeError, ValueError):
        return None


def build_profile(text: str, method: str, stored_name: str, original_name: str,
                  heur: dict, ai: Optional[dict]) -> dict:
    ai = ai or {}
    # --- skills: canonical ones for matching, plus extra ones the model found
    skills = list(heur["skills"])
    extra_display = []
    for s in ai.get("skills") or []:
        if not isinstance(s, str):
            continue
        canon = canonicalize(s)
        if canon:
            if canon not in skills:
                skills.append(canon)
        elif len(s) <= 30 and s.strip().lower() not in [e.lower() for e in extra_display]:
            extra_display.append(s.strip())

    # --- contact + links
    email = ai.get("email") if isinstance(ai.get("email"), str) and EMAIL_RE.fullmatch(ai["email"].strip()) else None
    email = (email or heur["email"] or None)
    email = email.strip() if email else None
    github = heur["github_url"]
    if not github and isinstance(ai.get("github"), str):
        m = GITHUB_RE.search(ai["github"])
        github = f"https://github.com/{m.group(1)}" if m else None
    linkedin = heur["linkedin_url"]
    if not linkedin and isinstance(ai.get("linkedin"), str):
        linkedin = safe_url(ai["linkedin"])

    # --- location
    loc = normalize_location(ai.get("location") if isinstance(ai.get("location"), str) else None)
    if not loc["city"] and not loc["country"]:
        loc = heur["location"]

    # --- education
    level = _LEVELS.get(str(ai.get("highest_education_level", "")).lower(), 0)
    degrees = [d for d in (ai.get("education") or []) if isinstance(d, dict)]
    edu_summary = None
    field = None
    if degrees:
        parts = []
        for d in degrees[:2]:
            bit = " ".join(x for x in [d.get("degree"), d.get("field")] if x)
            if d.get("institution"):
                bit += f" — {d['institution']}"
            if bit.strip():
                parts.append(bit.strip())
        edu_summary = "; ".join(parts) or None
        field = next((detect_field(f"{d.get('degree') or ''} {d.get('field') or ''}") for d in degrees
                      if detect_field(f"{d.get('degree') or ''} {d.get('field') or ''}")), None)
    if not level:
        level = detect_level(heur["education_text"])
    field = field or detect_field(heur["education_text"])
    edu_summary = edu_summary or (heur["education_text"].splitlines()[0] if heur["education_text"] else None)

    # --- experience
    exp = _num(ai.get("total_experience_years"))
    if exp is None:
        exp = heur["experience_years"]

    name = (ai.get("name") if isinstance(ai.get("name"), str) and ai.get("name").strip() else None) \
        or heur["name"] or Path(original_name).stem.replace("_", " ").replace("-", " ").title()

    key = (email or "").lower() or uuid.uuid4().hex
    cid = "cv:" + hashlib.sha1(key.encode()).hexdigest()[:10]

    return {
        "id": cid,
        "source": "cv",
        "name": name.strip(),
        "username": None,
        "headline": ai.get("headline") if isinstance(ai.get("headline"), str) else None,
        "location_raw": loc["display"] or None,
        "city": loc["city"],
        "country": loc["country"],
        "skills": skills,
        "extra_skills": extra_display[:10],
        "experience_years": exp,
        "experience_source": "cv",
        "education": {"level": level, "field": field, "text": edu_summary},
        "email": email,
        "phone": heur["phone"],
        "github_url": github,
        "linkedin_url": linkedin,
        "website": None,
        "cv_url": f"/cv/{stored_name}",
        "avatar_url": None,
        "top_repos": [],
        "projects": [p for p in (ai.get("projects") or []) if isinstance(p, str)][:5],
        "certifications": [c for c in (ai.get("certifications") or []) if isinstance(c, str)][:5],
        "followers": 0,
        "public_repos": 0,
        "last_active": None,
        "extraction": {"method": method, "ai_used": bool(ai), "chars": len(text)},
    }


async def process_cv(path: Path, original_name: str) -> dict:
    text, method = await run_in_threadpool(extract_text, path)
    if len(text.strip()) < 30:
        raise ValueError("No readable text found. Upload a clearer scan or a PDF with selectable text.")
    heur = heuristic_extract(text)
    ai = await llm_extract(text)
    return build_profile(text, method, path.name, original_name, heur, ai)


def summarize_education(profile: dict) -> str:
    edu = profile.get("education") or {}
    if edu.get("text"):
        return edu["text"]
    if edu.get("level"):
        return LEVEL_NAMES[edu["level"]] + (f" in {edu['field']}" if edu.get("field") else "")
    return "Unknown"
