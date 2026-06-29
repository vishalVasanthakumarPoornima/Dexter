from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.jobs.config import load_jobs_config
from backend.jobs.models import ApplicationProfile, Resume
from backend.profile.resume_parser import parse_resume_text
from backend.profile.skills import extract_skills


def get_or_create_default_profile(session: Session, config: dict | None = None) -> ApplicationProfile:
    cfg = config or load_jobs_config()
    existing = session.execute(select(ApplicationProfile).order_by(ApplicationProfile.id)).scalars().first()
    profile_cfg = cfg.get("profile", {})
    target_cfg = cfg.get("targets", {})
    parsed_text = parse_resume_text(profile_cfg.get("resume_path", ""))
    skills = extract_skills(parsed_text, profile_cfg.get("skills") or [])
    if not skills:
        skills = profile_cfg.get("skills") or ["Python", "React", "FastAPI", "SQL", "Automation"]

    if existing:
        if not existing.skills:
            existing.skills = skills
        return existing

    profile = ApplicationProfile(
        name=profile_cfg.get("name") or "Default",
        email=profile_cfg.get("email") or "",
        phone=profile_cfg.get("phone") or "",
        location=profile_cfg.get("location") or "",
        work_authorization=profile_cfg.get("work_authorization") or "",
        visa_notes=str(profile_cfg.get("sponsorship_needed") or ""),
        github_url=profile_cfg.get("github") or "",
        linkedin_url=profile_cfg.get("linkedin") or "",
        portfolio_url=profile_cfg.get("portfolio") or "",
        preferred_roles=target_cfg.get("roles") or [],
        preferred_locations=target_cfg.get("locations") or [],
        skills=skills,
        resume_path=profile_cfg.get("resume_path") or "",
    )
    session.add(profile)
    session.flush()
    if profile.resume_path:
        session.add(
            Resume(
                profile_id=profile.id,
                file_path=profile.resume_path,
                parsed_text=parsed_text,
                skills=skills,
                projects=[],
                experience=[],
            )
        )
    return profile
