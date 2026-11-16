"""Drafts the outreach e-mail (Groq if available, otherwise a clean template)."""
from typing import Optional

from . import llm
from .skills import display

SYSTEM = """You write short, polite recruiting outreach e-mails for a recruiter in Pakistan.
Return ONLY a JSON object: {"subject": string, "body": string}.
Rules: max 120 words in the body; plain text; start with "Hi <first name>,"; be honest and specific
(mention 1-2 of the candidate's real skills); say how you found them ("public GitHub profile" or "CV"),
do not invent salary, company details or promises; end by asking for a short call or a reply;
sign off with the recruiter's name and company."""


def _first_name(candidate: dict) -> str:
    name = (candidate.get("name") or candidate.get("username") or "there").strip()
    return name.split()[0] if name else "there"


def template_draft(candidate: dict, role: str, recruiter: str, company: str, kind: str) -> dict:
    skills = ", ".join(display(s) for s in candidate.get("skills", [])[:3])
    found = (f"your public GitHub profile ({candidate['github_url']})"
             if candidate.get("source") == "github" and candidate.get("github_url") else "your CV")
    what = "internship" if kind == "internship" else "job"
    subject = f"{role} {what} opportunity at {company}"
    body = (
        f"Hi {_first_name(candidate)},\n\n"
        f"I'm {recruiter} from {company}. I came across {found}"
        f"{' and your work with ' + skills if skills else ''}, and I think you could be a great fit "
        f"for our {role} {what}.\n\n"
        f"Would you be open to a short call or reply this week so I can share the details?\n\n"
        f"Best regards,\n{recruiter}\n{company}"
    )
    return {"subject": subject, "body": body}


async def make_draft(candidate: dict, role: Optional[str], recruiter: Optional[str],
                     company: Optional[str], kind: str) -> dict:
    role = (role or "Software Engineer").strip()
    recruiter = (recruiter or "Hiring Team").strip()
    company = (company or "our company").strip()
    kind = "internship" if kind == "internship" else "job"
    fallback = template_draft(candidate, role, recruiter, company, kind)
    if not llm.available():
        return fallback
    info = {
        "candidate_first_name": _first_name(candidate),
        "candidate_skills": [display(s) for s in candidate.get("skills", [])[:5]],
        "found_via": "public GitHub profile" if candidate.get("source") == "github" else "CV",
        "position": f"{role} ({kind})",
        "recruiter_name": recruiter,
        "company": company,
    }
    try:
        out = await llm.chat_json(SYSTEM, f"Write the e-mail for: {info}", max_tokens=500)
        subject, body = str(out.get("subject", "")).strip(), str(out.get("body", "")).strip()
        if subject and body:
            return {"subject": subject, "body": body}
    except Exception:
        pass
    return fallback
