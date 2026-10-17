"""CV -> structured profile data.

Uses Gemini when GEMINI_API_KEY is set, otherwise a basic keyword/regex fallback.
In both cases the result is only a *suggestion*: the student reviews it before it is saved.
"""
import re
from datetime import date

from common import ai

SKILL_LEVELS = {"beginner", "intermediate", "advanced"}
LANG_LEVELS = {"beginner", "intermediate", "advanced", "native"}
EXP_TYPES = {"internship", "job", "freelance", "other"}

PROMPT = """Tu analyses le texte d'un CV. Extrais les informations et réponds uniquement avec un objet JSON de la forme :
{{"headline": "", "bio": "", "linkedin_url": "", "github_url": "",
"skills": [{{"name": "", "level": "beginner|intermediate|advanced"}}],
"languages": [{{"name": "", "level": "beginner|intermediate|advanced|native"}}],
"educations": [{{"school": "", "degree": "", "field": "", "start_year": null, "end_year": null}}],
"experiences": [{{"position": "", "company": "", "type": "internship|job|freelance|other", "start_date": "YYYY-MM-DD ou null", "end_date": "YYYY-MM-DD ou null", "description": ""}}],
"projects": [{{"title": "", "description": "", "tech_stack": ""}}],
"certifications": [{{"name": "", "issuer": ""}}]}}
N'invente rien : laisse vide ou null ce qui n'est pas dans le CV. Conserve la langue du CV.

CV :
{text}
"""


def _s(value, limit):
    return str(value or "").strip()[:limit]


def _year(value):
    try:
        year = int(str(value)[:4])
        return year if 1950 <= year <= 2100 else None
    except (TypeError, ValueError):
        return None


def _date(value):
    match = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", str(value or "").strip())
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2) or 1), int(match.group(3) or 1)).isoformat()
    except ValueError:
        return None


def _url(value):
    value = _s(value, 200)
    return value if re.match(r"^https?://", value) else ""


def clean(raw):
    """Force any AI/heuristic output into the exact shape the API accepts."""
    raw = raw if isinstance(raw, dict) else {}

    def rows(key):
        return [r for r in (raw.get(key) if isinstance(raw.get(key), list) else []) if r]

    out = {
        "headline": _s(raw.get("headline"), 120),
        "bio": _s(raw.get("bio"), 1000),
        "linkedin_url": _url(raw.get("linkedin_url")),
        "github_url": _url(raw.get("github_url")),
        "skills": [], "languages": [], "educations": [], "experiences": [], "projects": [], "certifications": [],
    }
    for key, levels, default in (("skills", SKILL_LEVELS, "intermediate"), ("languages", LANG_LEVELS, "intermediate")):
        seen = set()
        for r in rows(key):
            r = {"name": r} if isinstance(r, str) else r
            if not isinstance(r, dict):
                continue
            name = _s(r.get("name"), 80)
            if name and name.lower() not in seen:
                seen.add(name.lower())
                level = r.get("level") if r.get("level") in levels else default
                out[key].append({"name": name, "level": level})
    for r in rows("educations"):
        if isinstance(r, dict) and _s(r.get("school"), 150):
            out["educations"].append({
                "school": _s(r.get("school"), 150), "degree": _s(r.get("degree"), 150), "field": _s(r.get("field"), 150),
                "start_year": _year(r.get("start_year")), "end_year": _year(r.get("end_year")),
            })
    for r in rows("experiences"):
        if not isinstance(r, dict):
            continue
        position = _s(r.get("position"), 150) or _s(r.get("company"), 150)
        if position:
            out["experiences"].append({
                "position": position, "company": _s(r.get("company"), 150),
                "type": r.get("type") if r.get("type") in EXP_TYPES else "other",
                "start_date": _date(r.get("start_date")), "end_date": _date(r.get("end_date")),
                "description": _s(r.get("description"), 1500),
            })
    for r in rows("projects"):
        if isinstance(r, dict) and _s(r.get("title"), 150):
            out["projects"].append({
                "title": _s(r.get("title"), 150), "description": _s(r.get("description"), 1500),
                "tech_stack": _s(r.get("tech_stack"), 250),
            })
    for r in rows("certifications"):
        if isinstance(r, dict) and _s(r.get("name"), 150):
            out["certifications"].append({"name": _s(r.get("name"), 150), "issuer": _s(r.get("issuer"), 150)})
    return out


# ---------------------------------------------------------------- heuristic fallback
SECTIONS = {
    "educations": r"formations?|éducation|education|études|etudes|parcours acad\w+|academic",
    "skills": r"compétences|competences|skills|technologies|outils|tools",
    "projects": r"projets?|projects?",
    "experiences": r"expériences?|experiences?|stages?|internships?|work history",
    "certifications": r"certifications?|certificats?|certificates?",
    "languages": r"langues?|languages?",
}
BULLET = re.compile(r"^[\s\-•*▪●◦·\u2022]+")
YEAR = re.compile(r"(?:19|20)\d{2}")
LANG_LEVEL_HINTS = [
    ("native", r"natif|native|maternelle|mother"),
    ("advanced", r"courant|fluent|bilingue|\bc1\b|\bc2\b|avancé|advanced"),
    ("beginner", r"débutant|beginner|\ba1\b|\ba2\b|notions|basic"),
    ("intermediate", r"intermédiaire|intermediate|\bb1\b|\bb2\b"),
]


def _split_sections(text):
    sections, current = {}, None
    for line in text.splitlines():
        stripped = line.strip().strip(":").strip()
        low = stripped.lower()
        heading = None
        if 0 < len(stripped.split()) <= 4 and len(stripped) <= 40:
            for key, pattern in SECTIONS.items():
                if re.match(rf"^(?:{pattern})\b", low):
                    heading = key
                    break
        if heading:
            current = heading
            sections.setdefault(current, [])
        elif current and stripped and "://" not in stripped and "@" not in stripped:
            sections[current].append(BULLET.sub("", line).strip())
    return sections


def _heuristic(text):
    sec = _split_sections(text)
    data = {"skills": [], "languages": [], "educations": [], "experiences": [], "projects": [], "certifications": []}

    for line in sec.get("skills", []):
        line = line.split(":", 1)[1] if ":" in line else line
        data["skills"] += [{"name": p.strip()} for p in re.split(r"[,;|•·/]", line) if 1 < len(p.strip()) <= 40]

    for line in sec.get("languages", []):
        for part in re.split(r"[,;|•]", line):
            name = re.split(r"[(\-–:]", part)[0].strip()
            if 1 < len(name) <= 30 and re.fullmatch(r"[^\W\d_]+(?: [^\W\d_]+){0,2}", name):
                level = next((lv for lv, pat in LANG_LEVEL_HINTS if re.search(pat, part.lower())), "intermediate")
                data["languages"].append({"name": name, "level": level})

    for line in sec.get("educations", []):
        years = YEAR.findall(line)
        if years:
            school = re.sub(r"(?:19|20)\d{2}|[–—\-/()|]+", " ", line)
            data["educations"].append({
                "school": " ".join(school.split()),
                "start_year": years[0] if len(years) > 1 else None,
                "end_year": years[-1],
            })

    for line in sec.get("experiences", []):
        years = YEAR.findall(line)
        if years:
            title = " ".join(re.sub(r"(?:19|20)\d{2}|[–—\-/()|]+", " ", line).split())
            data["experiences"].append({
                "position": title,
                "type": "internship" if re.search(r"stage|intern", line.lower()) else "job",
                "start_date": years[0], "end_date": years[-1] if len(years) > 1 else None,
            })

    data["projects"] = [{"title": l[:120]} for l in sec.get("projects", []) if 3 < len(l) <= 80]
    data["certifications"] = [{"name": l[:150]} for l in sec.get("certifications", []) if len(l) > 3]
    return data


def parse_cv(text):
    """Return (structured_data, method) where method is 'ai' or 'basic'."""
    data, method = None, "basic"
    if ai.is_configured():
        try:
            data, method = ai.generate_json(PROMPT.format(text=text[:15000])), "ai"
        except ai.AIError:
            data = None
    if data is None:
        data, method = _heuristic(text), "basic"
    data = clean(data)
    data["linkedin_url"] = data["linkedin_url"] or _url(next(iter(re.findall(r"https?://(?:www\.)?linkedin\.com/\S+", text)), ""))
    data["github_url"] = data["github_url"] or _url(next(iter(re.findall(r"https?://(?:www\.)?github\.com/\S+", text)), ""))
    return data, method
