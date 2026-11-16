"""Central configuration. Values come from the .env file in the project root."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
DB_PATH = DATA_DIR / "recruiter.db"
HR_SHEET_PATH = DATA_DIR / "HR_Shortlist.xlsx"

for _d in (DATA_DIR, UPLOAD_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _clean(value: str) -> str:
    """Treat empty values and the placeholder text from .env.example as 'not set'."""
    value = (value or "").strip().strip('"').strip("'")
    if value.lower().startswith("your_") or value.lower().endswith("_here"):
        return ""
    return value


GROQ_API_KEY = _clean(os.getenv("GROQ_API_KEY", ""))
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

GITHUB_TOKEN = _clean(os.getenv("GITHUB_TOKEN", ""))


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


MAX_GITHUB_CANDIDATES = _int("MAX_GITHUB_CANDIDATES", 30)
RESULTS_LIMIT = _int("RESULTS_LIMIT", 10)
CACHE_TTL_SECONDS = 12 * 3600
MAX_UPLOAD_MB = 10
ALLOWED_CV_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}


def groq_ready() -> bool:
    return bool(GROQ_API_KEY)
