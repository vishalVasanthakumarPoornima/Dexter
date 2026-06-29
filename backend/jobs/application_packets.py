from __future__ import annotations

import json
import re
from pathlib import Path

from backend.jobs.config import generated_dir
from backend.jobs.models import ApplicationPacket, ApplicationProfile, Job, JobScore, Resume


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")[:80] or "job"


def _keyword_list(job: Job, profile: ApplicationProfile) -> list[str]:
    blob = f"{job.title} {job.description} {' '.join(job.requirements or [])}".lower()
    keywords = []
    for skill in profile.skills or []:
        if skill.lower() in blob:
            keywords.append(skill)
    for token in ("python", "react", "typescript", "security", "ai", "backend", "api", "sql", "automation"):
        if token in blob and token not in [item.lower() for item in keywords]:
            keywords.append(token)
    return keywords[:16]


def build_packet_artifacts(job: Job, profile: ApplicationProfile, score: JobScore | None = None, resume_text: str = "") -> dict:
    target_dir = generated_dir() / "application_packets" / f"{job.id}-{_slug(job.company)}-{_slug(job.title)}"
    target_dir.mkdir(parents=True, exist_ok=True)
    keywords = _keyword_list(job, profile)
    blockers = []
    if not profile.resume_path:
        blockers.append("No resume path configured or uploaded.")
    if not profile.email:
        blockers.append("Profile email missing.")
    if job.restricted:
        blockers.append("Restricted source: manual/supervised only.")

    resume_suggestions = [
        f"# Resume Suggestions for {job.title} at {job.company}",
        "",
        "Do not fabricate experience. Use only projects and skills already in the profile/resume.",
        "",
        "## ATS Keywords",
        ", ".join(keywords) or "No explicit keyword overlap found.",
        "",
        "## Bullet Suggestions",
    ]
    for keyword in keywords[:6]:
        resume_suggestions.append(f"- Emphasize existing {keyword} work where it already appears in your resume or projects.")
    if not keywords:
        resume_suggestions.append("- Review the job manually; Dexter did not find enough overlap to tailor safely.")

    resume_draft = [
        f"# Tailored Resume Draft for {job.title} at {job.company}",
        "",
        "Generated from the configured profile/resume material. Review before using; do not add unsupported experience.",
        "",
        f"Base resume path: {profile.resume_path or 'not configured'}",
        "",
        "## Target Role",
        f"- Title: {job.title}",
        f"- Company: {job.company}",
        f"- Location: {job.location or 'Not specified'}",
        "",
        "## Safe ATS Emphasis",
    ]
    if keywords:
        resume_draft.extend([f"- {keyword}" for keyword in keywords])
    else:
        resume_draft.append("- No safe keyword emphasis detected from current profile/resume data.")
    resume_draft.extend(
        [
            "",
            "## Suggested Resume Edits",
            "Use these edits only where the underlying resume/profile already supports them.",
            *[f"- Move or strengthen an existing bullet that demonstrates {keyword}." for keyword in keywords[:6]],
            "",
            "## Existing Resume Text",
            resume_text.strip() or "No parsed resume text is available. Configure profile.resume_path to improve tailoring.",
        ]
    )

    cover_letter = [
        f"Dear {job.company} hiring team,",
        "",
        f"I am interested in the {job.title} role. My profile appears relevant because "
        f"{'; '.join((score.match_reasons if score else [])[:3]) or 'the role aligns with my software engineering targets'}.",
        "",
        "I would tailor my resume around the verified skills and projects already present in my profile, "
        "and I would avoid adding any experience that is not supported by my existing background.",
        "",
        "Best,",
        profile.name or "Applicant",
    ]
    short_answers = {
        "why_this_role": f"{job.title} matches these verified fit signals: {', '.join((score.match_reasons if score else [])[:4]) or 'role-family fit pending review'}.",
        "missing_info_checklist": blockers,
        "work_authorization": profile.work_authorization or "BLOCKER: profile work authorization is not configured.",
        "sponsorship": profile.visa_notes or "BLOCKER: sponsorship preference is not configured.",
    }

    resume_path = target_dir / "tailored_resume_draft.md"
    suggestions_path = target_dir / "resume_suggestions.md"
    cover_path = target_dir / "cover_letter_draft.md"
    answers_path = target_dir / "short_answers.json"
    resume_path.write_text("\n".join(resume_draft) + "\n", encoding="utf-8")
    suggestions_path.write_text("\n".join(resume_suggestions) + "\n", encoding="utf-8")
    cover_path.write_text("\n".join(cover_letter) + "\n", encoding="utf-8")
    answers_path.write_text(json.dumps(short_answers, indent=2), encoding="utf-8")

    return {
        "resume_variant_path": str(resume_path),
        "cover_letter_path": str(cover_path),
        "short_answers_json": short_answers,
        "resume_diff_summary": f"Generated tailored resume draft plus suggestions; base resume was not modified. Suggestions: {suggestions_path}",
        "recommendation": score.recommendation if score else "manual_review",
        "confidence": score.confidence if score else 0.5,
        "blockers": blockers,
    }


def upsert_packet(session, job: Job, profile: ApplicationProfile, score: JobScore | None = None) -> ApplicationPacket:
    packet = (
        session.query(ApplicationPacket)
        .filter(ApplicationPacket.job_id == job.id, ApplicationPacket.profile_id == profile.id)
        .one_or_none()
    )
    resume = session.query(Resume).filter(Resume.profile_id == profile.id).order_by(Resume.created_at.desc()).first()
    artifacts = build_packet_artifacts(job, profile, score, resume.parsed_text if resume else "")
    if packet is None:
        packet = ApplicationPacket(job_id=job.id, profile_id=profile.id, **artifacts)
        session.add(packet)
    else:
        for key, value in artifacts.items():
            setattr(packet, key, value)
    session.flush()
    return packet
