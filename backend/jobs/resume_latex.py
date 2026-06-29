from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.jobs.models import ApplicationProfile, Job, JobScore, Resume


LATEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def latex_escape(value: str | None) -> str:
    text = str(value or "")
    return "".join(LATEX_SPECIALS.get(char, char) for char in text)


def find_latex_compiler() -> str | None:
    for name in ("pdflatex", "xelatex", "tectonic"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")[:80] or "resume"


def _resume_lines(resume_text: str, limit: int = 8) -> list[str]:
    lines = []
    for raw in resume_text.splitlines():
        line = re.sub(r"\s+", " ", raw.strip(" -\t"))
        if len(line) < 18:
            continue
        if line.lower().startswith(("education", "experience", "projects", "skills")):
            continue
        lines.append(line[:180])
        if len(lines) >= limit:
            break
    return lines


def _keyword_list(job: Job, profile: ApplicationProfile) -> list[str]:
    blob = f"{job.title} {job.description} {' '.join(job.requirements or [])}".lower()
    keywords: list[str] = []
    for skill in profile.skills or []:
        if skill and skill.lower() in blob:
            keywords.append(skill)
    for token in ("Python", "React", "TypeScript", "JavaScript", "FastAPI", "SQL", "AWS", "AI", "ML", "Security", "Backend", "API"):
        if token.lower() in blob and token.lower() not in {item.lower() for item in keywords}:
            keywords.append(token)
    return keywords[:12]


def build_jake_resume_tex(job: Job, profile: ApplicationProfile, score: JobScore | None, resume_text: str) -> str:
    keywords = _keyword_list(job, profile)
    evidence = _resume_lines(resume_text)
    if not evidence:
        evidence = [
            "Configured profile/resume text was not available; review and replace this evidence section before applying.",
            "Use only verified projects, coursework, and experience from the base resume.",
        ]
    match_reasons = (score.match_reasons if score else [])[:4]
    if not match_reasons:
        match_reasons = ["role-family fit pending manual review"]

    name = profile.name or "Applicant"
    contact_parts = [profile.email, profile.phone, profile.location]
    links = [profile.linkedin_url, profile.github_url, profile.portfolio_url]
    contact_line = " $|$ ".join(latex_escape(part) for part in contact_parts + links if part)
    skill_line = ", ".join(latex_escape(item) for item in (keywords or profile.skills or [])[:16]) or "Review job keywords manually"

    evidence_items = "\n".join(f"      \\resumeItem{{{latex_escape(item)}}}" for item in evidence[:6])
    match_items = "\n".join(f"      \\resumeItem{{{latex_escape(item)}}}" for item in match_reasons)

    return rf"""\documentclass[letterpaper,11pt,oneside]{{article}}

\usepackage{{latexsym}}
\usepackage[empty]{{fullpage}}
\usepackage{{titlesec}}
\usepackage{{marvosym}}
\usepackage[usenames,dvipsnames]{{color}}
\usepackage{{verbatim}}
\usepackage{{enumitem}}
\usepackage[hidelinks]{{hyperref}}
\usepackage{{fancyhdr}}
\usepackage[english]{{babel}}
\usepackage{{tabularx}}
\IfFileExists{{glyphtounicode.tex}}{{\input{{glyphtounicode}}\pdfgentounicode=1}}{{}}

\pagestyle{{fancy}}
\fancyhf{{}}
\fancyfoot{{}}
\renewcommand{{\headrulewidth}}{{0pt}}
\renewcommand{{\footrulewidth}}{{0pt}}

\addtolength{{\oddsidemargin}}{{-0.5in}}
\addtolength{{\evensidemargin}}{{-0.5in}}
\addtolength{{\textwidth}}{{1in}}
\addtolength{{\topmargin}}{{-.5in}}
\addtolength{{\textheight}}{{1.0in}}

\urlstyle{{same}}
\raggedbottom
\raggedright
\setlength{{\tabcolsep}}{{0in}}

\titleformat{{\section}}{{\vspace{{-4pt}}\scshape\raggedright\large}}{{}}{{0em}}{{}}[\color{{black}}\titlerule \vspace{{-5pt}}]

\newcommand{{\resumeItem}}[1]{{\item\small{{{{#1 \vspace{{-2pt}}}}}}}}
\newcommand{{\resumeSubheading}}[4]{{
  \vspace{{-2pt}}\item
    \begin{{tabular*}}{{0.97\textwidth}}[t]{{l@{{\extracolsep{{\fill}}}}r}}
      \textbf{{#1}} & #2 \\
      \textit{{\small#3}} & \textit{{\small #4}} \\
    \end{{tabular*}}\vspace{{-7pt}}
}}
\newcommand{{\resumeProjectHeading}}[2]{{
    \item
    \begin{{tabular*}}{{0.97\textwidth}}{{l@{{\extracolsep{{\fill}}}}r}}
      \small#1 & #2 \\
    \end{{tabular*}}\vspace{{-7pt}}
}}
\newcommand{{\resumeSubItem}}[1]{{\resumeItem{{#1}}\vspace{{-4pt}}}}
\renewcommand\labelitemii{{$\vcenter{{\hbox{{\tiny$\bullet$}}}}$}}
\newcommand{{\resumeSubHeadingListStart}}{{\begin{{itemize}}[leftmargin=0.15in, label={{}}]}}
\newcommand{{\resumeSubHeadingListEnd}}{{\end{{itemize}}}}
\newcommand{{\resumeItemListStart}}{{\begin{{itemize}}}}
\newcommand{{\resumeItemListEnd}}{{\end{{itemize}}\vspace{{-5pt}}}}

\begin{{document}}

\begin{{center}}
    \textbf{{\Huge \scshape {latex_escape(name)}}} \\ \vspace{{1pt}}
    \small {contact_line}
\end{{center}}

\section{{Target}}
\resumeSubHeadingListStart
  \resumeProjectHeading{{\textbf{{{latex_escape(job.title)}}} $|$ \emph{{{latex_escape(job.company)}}}}}{{{latex_escape(job.location or "Location not specified")}}}
  \resumeItemListStart
{match_items}
  \resumeItemListEnd
\resumeSubHeadingListEnd

\section{{Technical Skills}}
\begin{{itemize}}[leftmargin=0.15in, label={{}}]
  \small{{\item{{\textbf{{Relevant Keywords}}{{: {skill_line}}}}}}}
\end{{itemize}}

\section{{Experience and Project Evidence}}
\resumeSubHeadingListStart
  \resumeProjectHeading{{\textbf{{Verified Base Resume Evidence}}}}{{Review before submitting}}
  \resumeItemListStart
{evidence_items}
  \resumeItemListEnd
\resumeSubHeadingListEnd

\section{{Application Notes}}
\resumeSubHeadingListStart
  \resumeProjectHeading{{\textbf{{Safety Check}}}}{{Generated by Dexter}}
  \resumeItemListStart
      \resumeItem{{This draft uses Jake's resume template structure and is generated from configured profile/resume text.}}
      \resumeItem{{Do not submit until every bullet is verified against the base resume and the target job.}}
      \resumeItem{{Base resume path: {latex_escape(profile.resume_path or "not configured")}.}}
  \resumeItemListEnd
\resumeSubHeadingListEnd

\end{{document}}
"""


def compile_latex(tex_path: Path, compiler: str) -> tuple[Path | None, str]:
    work_dir = tex_path.parent
    try:
        if Path(compiler).name == "tectonic":
            result = subprocess.run(
                [compiler, "--outdir", str(work_dir), str(tex_path)],
                cwd=work_dir,
                text=True,
                capture_output=True,
                timeout=45,
                check=False,
            )
        else:
            result = subprocess.run(
                [compiler, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
                cwd=work_dir,
                text=True,
                capture_output=True,
                timeout=45,
                check=False,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)

    pdf_path = tex_path.with_suffix(".pdf")
    if result.returncode == 0 and pdf_path.exists():
        return pdf_path, ""
    return None, (result.stdout + "\n" + result.stderr)[-4000:]


def export_jake_resume(session: Session, job_id: int, profile_id: int | None = None, prefer_pdf: bool = True) -> dict[str, Any]:
    profile = session.get(ApplicationProfile, profile_id) if profile_id else session.query(ApplicationProfile).order_by(ApplicationProfile.id).first()
    job = session.get(Job, job_id)
    if job is None:
        return {"ok": False, "error": f"Unknown job id: {job_id}"}
    if profile is None:
        return {"ok": False, "error": "No application profile is configured."}

    score = session.query(JobScore).filter(JobScore.job_id == job.id, JobScore.profile_id == profile.id).one_or_none()
    resume = session.query(Resume).filter(Resume.profile_id == profile.id).order_by(Resume.created_at.desc()).first()
    resume_text = resume.parsed_text if resume else ""
    export_dir = Path(tempfile.mkdtemp(prefix="dexter_resume_export_"))
    basename = f"{job.id}-{_slug(job.company)}-{_slug(job.title)}-jake-resume"
    tex_path = export_dir / f"{basename}.tex"
    tex_path.write_text(build_jake_resume_tex(job, profile, score, resume_text), encoding="utf-8")

    compiler = find_latex_compiler()
    if prefer_pdf and compiler:
        pdf_path, compile_error = compile_latex(tex_path, compiler)
        if pdf_path:
            return {
                "ok": True,
                "path": str(pdf_path),
                "filename": pdf_path.name,
                "media_type": "application/pdf",
                "compiled": True,
                "compiler": Path(compiler).name,
            }
        return {
            "ok": True,
            "path": str(tex_path),
            "filename": tex_path.name,
            "media_type": "application/x-tex",
            "compiled": False,
            "compiler": Path(compiler).name,
            "compile_error": compile_error,
        }

    return {
        "ok": True,
        "path": str(tex_path),
        "filename": tex_path.name,
        "media_type": "application/x-tex",
        "compiled": False,
        "compiler": None,
        "compile_error": "No LaTeX compiler found. Install pdflatex, xelatex, or tectonic to export PDF automatically.",
    }
