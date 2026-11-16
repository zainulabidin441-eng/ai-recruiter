# Zig Recruitbot

A chatbot that helps recruiters find technical candidates in Pakistan.
Type what you need in plain English, for example:

> I want a 3 year experienced Python developer in Islamabad with FastAPI

The bot understands the requirements, searches **GitHub live**, also reads **uploaded CVs**
(PDF, scanned CV or photo, using computer vision + OCR), ranks everyone with an
**explainable match score**, and lets you **shortlist, reject or email** each candidate.
Shortlisted candidates are saved to an **HR sheet (Excel)**.

The AI only supports the decision. It does not decide who gets hired.
The match % means "how closely the available profile data fits your requirements", not a hiring prediction.

---

## 1. Setup (about 10 minutes)

You need **Python 3.10, 3.11 or 3.12**.

```bash
# 1) open a terminal inside the project folder (ai_recruiter)

# 2) create a virtual environment
python -m venv venv

# 3) activate it
#    Windows:
venv\Scripts\activate
#    Mac / Linux:
source venv/bin/activate

# 4) install everything (first install downloads ~150 MB, OCR models are included)
pip install -r requirements.txt

# 5) create your settings file
#    Windows:   copy .env.example .env
#    Mac/Linux: cp .env.example .env
```

### Get the two free keys and put them in `.env`

| Key | Where to get it | Why |
|-----|-----------------|-----|
| `GROQ_API_KEY` | https://console.groq.com/keys (free account) | Understands the chat message, reads CV text, writes emails |
| `GITHUB_TOKEN` | https://github.com/settings/tokens → *Generate new token (classic)* → **no scopes needed** | GitHub only allows ~60 requests/hour without a token, which is too little for searching |

Open `.env` in any text editor and paste the keys after the `=` signs.

> The app still starts without the keys: without Groq it uses a simpler rule-based
> understanding of your message, and without a GitHub token it is limited to ~10 profiles per search.
> The top bar shows which keys are detected.

### Run

```bash
python run.py
```

The browser opens at **http://127.0.0.1:8000**. Stop the server with `Ctrl + C`.

---

## 2. How to use it

1. **Search** – type a request, or click one of the example chips.
   Examples: `Python developer in Islamabad`, `ML engineer in Lahore`, `Django developer from Karachi`, `AI engineer in Rawalpindi`.
2. **Refine** – follow up with `make it Lahore` or `also needs Docker`.
3. **Read the results** – each card shows the match %, skills (green = found, amber = related, red = missing),
   location, experience, education, and links to **GitHub / LinkedIn / CV / email** when they exist.
   Press **Why 94%?** to see the score breakdown.
4. **Decide** – **Shortlist** (saved to the HR sheet), **Reject** (hidden in later searches), or **Contact**
   (writes an email draft you can edit, then opens your mail app or Gmail).
5. **Upload CVs** – click the paperclip (or drag files into the chat). The CV is read, turned into a profile,
   scored, and included in every later search.
6. **HR sheet** – the *Shortlist* panel has **Download HR sheet (.xlsx)**. A copy is also kept at `data/HR_Shortlist.xlsx`.

---

## 3. How it works

```
Recruiter message
   -> Groq LLM: extract role, skills, experience, city, education (JSON)
   -> GitHub Search API: users in that city + language, then profile + repos for each
   -> Candidate profiles (GitHub + uploaded CVs)
   -> Matching engine (plain Python, weighted score)
   -> Ranked, explainable results -> Shortlist / Reject / Contact
```

**Computer vision / CV pipeline** (`app/cv_processor.py`)

```
PDF / scan / photo
  -> PyMuPDF text layer (digital PDFs)
  -> OpenCV clean-up (resize, deskew, contrast) + RapidOCR (scans, photos, image-only PDF pages)
  -> Groq extraction (falls back to rule-based extraction)
  -> name, email, phone, skills, experience, education, projects, certifications, location, links
```

**Match score** (`app/matcher.py`) – a weighted average of only the things you asked for:

| Dimension | Weight | Rule |
|-----------|--------|------|
| Skills | 45% | exact = 100%, related skill (e.g. Flask for FastAPI) = 60%, language only = 25% |
| Experience | 25% | candidate years / required years (max 100%) |
| Location | 20% | same city 100%, twin city (Islamabad/Rawalpindi) 80%, Pakistan only 50%, other city 30% |
| Education | 10% | degree level and field |

If information is **unknown** (for example education on GitHub), it shows as *Unknown* and is
**left out of the score**. It is never counted as 0% or 100%.

---

## 4. Project structure

```
ai_recruiter/
├── run.py                  start the app
├── requirements.txt
├── .env.example            copy to .env and add your keys
├── app/
│   ├── main.py             FastAPI routes (chat, upload, shortlist, HR sheet, email)
│   ├── requirement_parser.py   chat message -> structured requirements
│   ├── github_search.py    live GitHub search + profile building
│   ├── cv_processor.py    OpenCV + OCR + CV information extraction
│   ├── matcher.py          scoring and ranking with explanations
│   ├── skills.py           skill vocabulary and related skills
│   ├── locations.py        Pakistani city normalisation (ISB, Pindi, ...)
│   ├── education.py        education level / field detection
│   ├── emailer.py          outreach email drafts
│   ├── hr_sheet.py         Excel HR sheet
│   ├── llm.py              Groq client
│   ├── database.py         SQLite (cache, candidates, decisions)
│   └── config.py
├── static/                 index.html, style.css, app.js (the chat UI)
└── data/                   created automatically: database, uploaded CVs, HR sheet
```

---

## 5. Honest limitations (good to mention in your report / viva)

- **GitHub has no education field and no work history.** Experience is *estimated* from the age of the
  person's first own repository and is labelled as an estimate. Exact years and education come from CVs.
- **Location is free text** written by users. The app understands many Pakistani spellings
  (ISB, Pindi, Lahore, Punjab...), but people who write no location are not found.
- **Email is only used when it is public** on the GitHub profile or inside an uploaded CV.
  Emails are never collected from commit history. LinkedIn is **never scraped**; the link is shown only when
  the person lists it on GitHub or in their CV.
- **GitHub's terms** limit using user data for unsolicited marketing. Use the contact feature for genuine,
  individual job or internship outreach, and mention this in your report.
- Skills from GitHub are detected from repository languages, topics, names, descriptions and bio, so
  a good developer with private or unlabelled work can be under-scored. That is why the score is only decision support.
- Free tiers have rate limits (GitHub and Groq). Results are cached for 12 hours in SQLite.

## 6. Troubleshooting

| Problem | Fix |
|---------|-----|
| `GitHub API rate limit reached` | Add `GITHUB_TOKEN` to `.env`, restart, or wait a few minutes |
| `GitHub rejected your GITHUB_TOKEN` | Create a new classic token (no scopes) and paste it again |
| Top bar says "Groq key missing" | Check `GROQ_API_KEY` in `.env` (no quotes, no spaces) and restart |
| CV says "No readable text found" | Upload a sharper scan (at least 150 DPI) or the original PDF |
| First CV upload is slow | OCR models load once (about 5–10 seconds); later uploads are faster |
| `pip install` fails for `rapidocr-onnxruntime` | Use Python 3.10–3.12 (onnxruntime does not support 3.13 yet) |
| Port 8000 already in use | Change `PORT` in `run.py` |

## 7. Ideas if you have time left

Better semantic matching with sentence-transformers, a LangGraph agent workflow, a dashboard of
shortlist statistics, more sources (Stack Overflow, Kaggle), and a CV generator that formats a candidate profile as a PDF.
