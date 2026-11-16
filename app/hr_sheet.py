"""HR sheet: every shortlisted candidate is written to an Excel workbook."""
import io
import threading
from datetime import datetime
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import config
from .cv_processor import summarize_education
from .skills import display

_lock = threading.Lock()

HEADERS = ["#", "Date shortlisted", "Name", "Source", "Location", "Match %", "Experience",
           "Education", "Key skills", "Email", "Send email", "GitHub", "LinkedIn", "CV file",
           "Search query"]
WIDTHS = [5, 18, 26, 12, 20, 10, 24, 34, 40, 30, 14, 14, 14, 12, 44]


def _experience(c: dict) -> str:
    y = c.get("experience_years")
    if y is None:
        return "Unknown"
    return f"~{y:g} yrs (GitHub estimate)" if c.get("experience_source") == "github_estimate" else f"{y:g} yrs"


def _link(cell, url, label):
    if url:
        cell.value = label
        cell.hyperlink = url
        cell.font = Font(color="4F46E5", underline="single")
    else:
        cell.value = "—"
        cell.font = Font(color="9CA3AF")


def build_workbook(rows: list, base_url: str = "") -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Shortlisted candidates"
    ws.append(HEADERS)

    head_fill = PatternFill("solid", fgColor="4F46E5")
    thin = Side(style="thin", color="E5E7EB")
    for i, cell in enumerate(ws[1], start=1):
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = WIDTHS[i - 1]
    ws.row_dimensions[1].height = 24

    base = base_url.rstrip("/")
    for n, row in enumerate(rows, start=1):
        c = row["candidate"]
        r = n + 1
        email = c.get("email")
        subject = "Opportunity at our company"
        mailto = f"mailto:{email}?subject={quote(subject)}" if email else None
        cv_url = f"{base}{c['cv_url']}" if c.get("cv_url") else None
        skills = ", ".join(display(s) for s in c.get("skills", [])[:10])
        values = [
            n,
            datetime.fromtimestamp(row["updated"]).strftime("%Y-%m-%d %H:%M"),
            c.get("name"),
            "GitHub" if c.get("source") == "github" else "Uploaded CV",
            c.get("location_raw") or "Unknown",
            (row["match_score"] / 100) if row["match_score"] is not None else None,
            _experience(c),
            summarize_education(c),
            skills,
            email or "Not available",
            None, None, None, None,
            row.get("query") or "",
        ]
        ws.append(values)
        ws.cell(r, 6).number_format = "0%"
        _link(ws.cell(r, 11), mailto, "Email")
        _link(ws.cell(r, 12), c.get("github_url"), "GitHub")
        _link(ws.cell(r, 13), c.get("linkedin_url"), "LinkedIn")
        _link(ws.cell(r, 14), cv_url, "Open CV")
        for col in range(1, len(HEADERS) + 1):
            cell = ws.cell(r, col)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=thin)
    ws.freeze_panes = "D2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{len(rows) + 1}"
    return wb


def workbook_bytes(rows: list, base_url: str = "") -> bytes:
    buf = io.BytesIO()
    build_workbook(rows, base_url).save(buf)
    return buf.getvalue()


def save_to_disk(rows: list, base_url: str = "") -> bool:
    """Best-effort copy at data/HR_Shortlist.xlsx (fails quietly if Excel has it open)."""
    with _lock:
        try:
            build_workbook(rows, base_url).save(config.HR_SHEET_PATH)
            return True
        except PermissionError:
            return False
