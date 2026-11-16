"""FastAPI application: chat search, CV upload, shortlist / reject, HR sheet, e-mail drafts."""
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, cv_processor, database, emailer, github_search, hr_sheet, llm, matcher
from . import requirement_parser
from .skills import display


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.init_db()
    yield


app = FastAPI(title="Zig RecruitBot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")



# ------------------------------------------------------------------- models
class ChatIn(BaseModel):
    message: str
    previous_requirements: Optional[dict] = None


class DecisionIn(BaseModel):
    candidate_id: str
    match_score: Optional[float] = None
    query: Optional[str] = None


class EmailDraftIn(BaseModel):
    candidate_id: str
    job_role: Optional[str] = None
    recruiter_name: Optional[str] = None
    company: Optional[str] = None
    kind: str = "job"


# ------------------------------------------------------------------ helpers
def _public_candidate(c: dict, shortlisted: set) -> dict:
    """Candidate as sent to the browser (adds display names + status)."""
    out = dict(c)
    out["skills_display"] = [display(s) for s in c.get("skills", [])] + c.get("extra_skills", [])
    out["status"] = "shortlisted" if c["id"] in shortlisted else None
    return out


def _require_candidate(candidate_id: str) -> dict:
    cand = database.get_candidate(candidate_id)
    if not cand:
        raise HTTPException(404, "Candidate not found. Run the search again.")
    return cand


# -------------------------------------------------------------------- pages
@app.get("/")
def index():
    return FileResponse(config.STATIC_DIR / "index.html")

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(config.STATIC_DIR / "favicon.ico")


@app.get("/api/status")
def status():
    return {
        "groq": config.groq_ready(),
        "github_token": bool(config.GITHUB_TOKEN),
        "model": config.GROQ_MODEL if config.groq_ready() else None,
        "shortlist_count": len(database.ids_with_status("shortlisted")),
    }


# --------------------------------------------------------------------- chat
@app.post("/api/chat")
async def chat(body: ChatIn):
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Please type a message.")

    parsed = await requirement_parser.parse(message, body.previous_requirements)
    
    if parsed["intent"] != "search":
        return {"reply": parsed["reply"], "requirements": body.previous_requirements,
                "candidates": [], "warnings": [], "searched": False}


    req = parsed["requirements"]
    warnings, pool, gh_count = [], [], 0
    try:
        gh_profiles, gh_warnings = await github_search.search_github(req)
        pool += gh_profiles
        gh_count = len(gh_profiles)
        warnings += gh_warnings
    except github_search.GitHubError as e:
        warnings.append(str(e))
    except httpx.HTTPError:
        warnings.append("Could not reach GitHub. Check your internet connection.")

    cv_profiles = database.list_cv_candidates()
    pool += cv_profiles
    database.save_candidates(pool)

    rejected = database.ids_with_status("rejected")
    shortlisted = database.ids_with_status("shortlisted")
    pool = [p for p in pool if p["id"] not in rejected]
    ranked = matcher.rank(pool, req)[: config.RESULTS_LIMIT]

    if ranked:
        top = ranked[0]
        reply = (f"I found {len(ranked)} candidates for {req['summary']}. "
                 f"Best match: {top['name']} at {top['match']['score']}%. "
                 f"Open \"Why this score?\" on any card to see the breakdown.")
        if req.get("min_experience_years"):
            reply += " Experience from GitHub is an estimate based on account activity; a CV gives exact years."
    else:
        reply = (f"I couldn't find candidates for {req['summary']}. "
                 "Try fewer skills, a nearby city, or upload CVs to add more people.")
    return {
        "reply": reply,
        "requirements": req,
        "candidates": [_public_candidate(c, shortlisted) for c in ranked],
        "warnings": warnings,
        "searched": True,
        "stats": {"github_analyzed": gh_count, "cvs": len(cv_profiles)},
    }


# ---------------------------------------------------------------- CV upload
@app.post("/api/cv/upload")
async def upload_cv(files: list[UploadFile] = File(...), requirements: Optional[str] = Form(None)):
    req = None
    if requirements:
        try:
            req = json.loads(requirements)
        except json.JSONDecodeError:
            req = None

    shortlisted = database.ids_with_status("shortlisted")
    results, errors = [], []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in config.ALLOWED_CV_EXTENSIONS:
            errors.append(f"{f.filename}: unsupported file type (use PDF, PNG or JPG).")
            continue
        data = await f.read()
        if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
            errors.append(f"{f.filename}: file is larger than {config.MAX_UPLOAD_MB} MB.")
            continue
        path = config.UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
        path.write_bytes(data)
        try:
            profile = await cv_processor.process_cv(path, f.filename or "candidate")
        except Exception as e:  # unreadable file, OCR missing, etc.
            path.unlink(missing_ok=True)
            errors.append(f"{f.filename}: {e}")
            continue
        database.save_candidate(profile)
        item = _public_candidate(profile, shortlisted)
        if req and (req.get("skills") or req.get("location") or req.get("min_experience_years") is not None):
            item["match"] = matcher.score_candidate(profile, req)
        results.append(item)

    unique = {c["id"]: c for c in results}  # same person uploaded twice -> keep the latest
    results = list(unique.values())
    if req:
        results.sort(key=lambda c: c.get("match", {}).get("score", 0), reverse=True)
    return {"candidates": results, "errors": errors}


@app.get("/cv/{filename}")
def get_cv(filename: str):
    path = config.UPLOAD_DIR / Path(filename).name  # .name blocks path traversal
    if not path.is_file():
        raise HTTPException(404, "CV file not found.")
    return FileResponse(path)


# ----------------------------------------------------- shortlist / reject
@app.post("/api/shortlist")
def shortlist(body: DecisionIn, request: Request):
    cand = _require_candidate(body.candidate_id)
    database.set_decision(body.candidate_id, "shortlisted", body.match_score, body.query)
    rows = database.shortlist_rows()
    saved = hr_sheet.save_to_disk(rows, str(request.base_url))
    return {"ok": True, "count": len(rows), "hr_sheet_url": "/api/hr-sheet",
            "saved_to_disk": saved, "email": cand.get("email"), "name": cand.get("name")}


@app.post("/api/unshortlist")
def unshortlist(body: DecisionIn, request: Request):
    database.clear_decision(body.candidate_id)
    rows = database.shortlist_rows()
    hr_sheet.save_to_disk(rows, str(request.base_url))
    return {"ok": True, "count": len(rows)}


@app.post("/api/reject")
def reject(body: DecisionIn):
    _require_candidate(body.candidate_id)
    database.set_decision(body.candidate_id, "rejected", body.match_score, body.query)
    return {"ok": True}


@app.post("/api/reset-rejected")
def reset_rejected():
    return {"ok": True, "restored": database.reset_rejected()}


@app.get("/api/shortlist")
def list_shortlist():
    items = []
    for row in database.shortlist_rows():
        c = row["candidate"]
        items.append({
            "id": c["id"], "name": c.get("name"), "match_score": row["match_score"],
            "email": c.get("email"), "github_url": c.get("github_url"),
            "linkedin_url": c.get("linkedin_url"), "cv_url": c.get("cv_url"),
            "location": c.get("location_raw"), "source": c.get("source"),
        })
    return {"items": items}


@app.get("/api/hr-sheet")
def download_hr_sheet(request: Request):
    data = hr_sheet.workbook_bytes(database.shortlist_rows(), str(request.base_url))
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="HR_Shortlist.xlsx"'},
    )


# -------------------------------------------------------------- e-mail draft
@app.post("/api/email-draft")
async def email_draft(body: EmailDraftIn):
    cand = _require_candidate(body.candidate_id)
    draft = await emailer.make_draft(cand, body.job_role, body.recruiter_name, body.company, body.kind)
    return {"email": cand.get("email"), "has_email": bool(cand.get("email")), **draft}
