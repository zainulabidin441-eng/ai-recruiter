"""Skill vocabulary: canonical names, aliases, related skills and text extraction."""
import re
from typing import Optional

# canonical name -> aliases (all lowercase)
SKILLS = {
    # languages
    "python": ["python", "python3"],
    "javascript": ["javascript", "js", "ecmascript"],
    "typescript": ["typescript"],
    "java": ["java", "core java"],
    "c++": ["c++", "cpp"],
    "c#": ["c#", "csharp"],
    "go": ["golang"],
    "php": ["php"],
    "ruby": ["ruby"],
    "rust": ["rust"],
    "kotlin": ["kotlin"],
    "swift": ["swift"],
    "dart": ["dart"],
    "sql": ["sql", "t-sql", "plsql", "pl/sql"],
    "html": ["html", "html5"],
    "css": ["css", "css3"],
    # backend / web frameworks
    "django": ["django", "django rest framework", "drf"],
    "flask": ["flask"],
    "fastapi": ["fastapi", "fast api", "fastapl"],
    "node.js": ["node.js", "nodejs"],
    "express": ["express.js", "expressjs", "express js"],
    "react": ["react", "react.js", "reactjs"],
    "react native": ["react native", "react-native"],
    "angular": ["angular", "angularjs"],
    "vue": ["vue", "vue.js", "vuejs"],
    "next.js": ["next.js", "nextjs"],
    "spring": ["spring boot", "springboot", "spring framework"],
    "laravel": ["laravel"],
    "ruby on rails": ["ruby on rails", "rails"],
    ".net": [".net", "dotnet", "asp.net", "asp.net core"],
    "flutter": ["flutter"],
    "android": ["android"],
    "ios": ["ios"],
    "wordpress": ["wordpress"],
    "tailwind": ["tailwind", "tailwindcss"],
    "bootstrap": ["bootstrap"],
    "rest api": ["rest api", "rest apis", "restful", "restful api", "restful apis"],
    "graphql": ["graphql"],
    "microservices": ["microservices", "microservice"],
    "firebase": ["firebase"],
    # data / AI
    "machine learning": ["machine learning", "machine-learning", "ml"],
    "deep learning": ["deep learning", "deep-learning", "neural network", "neural networks"],
    "nlp": ["nlp", "natural language processing"],
    "computer vision": ["computer vision", "computer-vision", "opencv", "image processing"],
    "data science": ["data science", "data-science", "data scientist"],
    "data analysis": ["data analysis", "data analytics", "data-analysis"],
    "tensorflow": ["tensorflow"],
    "pytorch": ["pytorch"],
    "keras": ["keras"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "pandas": ["pandas"],
    "numpy": ["numpy"],
    "generative ai": ["generative ai", "genai", "gen ai", "llm", "llms", "large language models"],
    "langchain": ["langchain"],
    "hugging face": ["huggingface", "hugging face"],
    "power bi": ["power bi", "powerbi"],
    "tableau": ["tableau"],
    "web scraping": ["web scraping", "scrapy", "beautifulsoup"],
    # databases
    "mysql": ["mysql"],
    "postgresql": ["postgresql", "postgres"],
    "mongodb": ["mongodb", "mongo"],
    "redis": ["redis"],
    # devops / cloud
    "docker": ["docker"],
    "kubernetes": ["kubernetes", "k8s"],
    "aws": ["aws", "amazon web services"],
    "azure": ["azure"],
    "gcp": ["gcp", "google cloud"],
    "ci/cd": ["ci/cd", "cicd", "github actions", "jenkins"],
    "linux": ["linux"],
    "terraform": ["terraform"],
    # misc
    "selenium": ["selenium"],
    "blockchain": ["blockchain", "solidity", "web3"],
    "cybersecurity": ["cybersecurity", "penetration testing", "ethical hacking"],
    "unity": ["unity3d", "unity engine"],
    "ui/ux": ["ui/ux", "ux design", "figma"],
}

DISPLAY = {
    "javascript": "JavaScript", "typescript": "TypeScript", "c++": "C++", "c#": "C#", "go": "Go",
    "php": "PHP", "sql": "SQL", "html": "HTML", "css": "CSS", "django": "Django", "fastapi": "FastAPI",
    "node.js": "Node.js", "express": "Express", "react": "React", "react native": "React Native",
    "next.js": "Next.js", "ruby on rails": "Ruby on Rails", ".net": ".NET", "ios": "iOS",
    "rest api": "REST API", "graphql": "GraphQL", "nlp": "NLP", "tensorflow": "TensorFlow",
    "pytorch": "PyTorch", "scikit-learn": "scikit-learn", "generative ai": "Generative AI",
    "hugging face": "Hugging Face", "power bi": "Power BI", "mysql": "MySQL",
    "postgresql": "PostgreSQL", "mongodb": "MongoDB", "aws": "AWS", "gcp": "GCP", "ci/cd": "CI/CD",
    "ui/ux": "UI/UX", "langchain": "LangChain", "numpy": "NumPy", "wordpress": "WordPress",
    "web scraping": "Web Scraping", "machine learning": "Machine Learning",
    "deep learning": "Deep Learning", "computer vision": "Computer Vision",
    "data science": "Data Science", "data analysis": "Data Analysis", "firebase": "Firebase",
    "tailwind": "Tailwind CSS", "cybersecurity": "Cybersecurity",
}

# Skills that earn partial credit if the candidate has a closely related skill.
RELATED = {
    "machine learning": ["deep learning", "scikit-learn", "tensorflow", "pytorch", "keras",
                         "data science", "nlp", "computer vision", "generative ai", "hugging face"],
    "deep learning": ["tensorflow", "pytorch", "keras", "computer vision", "nlp", "machine learning"],
    "data science": ["machine learning", "pandas", "numpy", "data analysis", "scikit-learn"],
    "data analysis": ["pandas", "data science", "power bi", "tableau", "numpy"],
    "nlp": ["hugging face", "langchain", "generative ai", "deep learning"],
    "generative ai": ["langchain", "hugging face", "nlp", "deep learning"],
    "computer vision": ["deep learning", "tensorflow", "pytorch"],
    "fastapi": ["flask", "django"],
    "flask": ["fastapi", "django"],
    "django": ["flask", "fastapi"],
    "react": ["next.js", "react native", "angular", "vue"],
    "next.js": ["react"],
    "react native": ["react", "flutter"],
    "angular": ["react", "vue"],
    "vue": ["react", "angular"],
    "node.js": ["express", "next.js"],
    "express": ["node.js"],
    "javascript": ["typescript", "node.js", "react", "angular", "vue", "next.js"],
    "typescript": ["javascript"],
    "mysql": ["postgresql", "sql"],
    "postgresql": ["mysql", "sql"],
    "sql": ["mysql", "postgresql"],
    "mongodb": ["firebase"],
    "aws": ["azure", "gcp"],
    "azure": ["aws", "gcp"],
    "gcp": ["aws", "azure"],
    "docker": ["kubernetes"],
    "kubernetes": ["docker"],
    "rest api": ["fastapi", "django", "flask", "express", "node.js", "spring", "laravel"],
    "flutter": ["dart", "react native"],
    "android": ["kotlin", "flutter", "react native"],
    "ios": ["swift", "flutter", "react native"],
    "laravel": ["php"],
    "spring": ["java"],
}

# Framework / topic -> programming language it implies (used for GitHub language search
# and for small "language only" partial credit).
IMPLIED_LANGUAGE = {
    "django": "python", "flask": "python", "fastapi": "python", "machine learning": "python",
    "deep learning": "python", "data science": "python", "data analysis": "python",
    "nlp": "python", "computer vision": "python", "tensorflow": "python", "pytorch": "python",
    "keras": "python", "scikit-learn": "python", "pandas": "python", "numpy": "python",
    "generative ai": "python", "langchain": "python", "hugging face": "python",
    "web scraping": "python",
    "react": "javascript", "node.js": "javascript", "express": "javascript",
    "next.js": "javascript", "angular": "typescript", "vue": "javascript",
    "react native": "javascript",
    "spring": "java", "laravel": "php", "flutter": "dart", "android": "kotlin",
    "ruby on rails": "ruby", ".net": "c#",
}

# Skills for which Python users often publish only Jupyter notebooks.
NOTEBOOK_SKILLS = {"machine learning", "deep learning", "data science", "data analysis", "nlp",
                   "computer vision", "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch"}

# Languages that GitHub's `language:` search qualifier understands for our vocabulary.
GITHUB_LANGUAGES = {"python", "javascript", "typescript", "java", "c++", "c#", "go", "php",
                    "ruby", "rust", "kotlin", "swift", "dart"}

# ------------------------------------------------------------------ internals
_ALIAS_TO_CANON = {}
for _canon, _aliases in SKILLS.items():
    _ALIAS_TO_CANON[_canon] = _canon
    for _a in _aliases:
        _ALIAS_TO_CANON[_a] = _canon

_ALL_ALIASES = sorted(_ALIAS_TO_CANON.keys(), key=len, reverse=True)
_PATTERN = re.compile(
    r"(?<![a-z0-9+#.])(" + "|".join(re.escape(a) for a in _ALL_ALIASES) + r")(?![a-z0-9+#])",
    re.IGNORECASE,
)


def canonicalize(term: str) -> Optional[str]:
    """Map a free-text skill name to its canonical key, or None if unknown."""
    if not term:
        return None
    t = term.strip().lower()
    for candidate in (t, t.replace("-", " "), t.replace("_", " "), t.replace(" ", "")):
        if candidate in _ALIAS_TO_CANON:
            return _ALIAS_TO_CANON[candidate]
    return None


_COMPACT_ALIASES = [(a.replace(" ", "").replace("-", ""), c) for a, c in _ALIAS_TO_CANON.items()
                    if len(a.replace(" ", "").replace("-", "")) >= 6
                    and a.replace(" ", "").replace("-", "").isalpha()]


def extract_skills(text: str, tolerant: bool = False) -> list:
    """Find known skills in free text. Returns canonical keys in order of first appearance.

    tolerant=True also matches skills whose spaces were lost by OCR ("MachineLearning").
    """
    if not text:
        return []
    low = text.lower()
    found = []
    for m in _PATTERN.finditer(low):
        canon = _ALIAS_TO_CANON[m.group(1).lower()]
        if canon not in found:
            found.append(canon)
    if tolerant:
        compact = re.sub(r"[^a-z]", "", low)
        for alias, canon in _COMPACT_ALIASES:
            if canon not in found and alias in compact:
                found.append(canon)
    return found


def display(skill: str) -> str:
    if skill in DISPLAY:
        return DISPLAY[skill]
    return skill.title() if skill.islower() else skill
