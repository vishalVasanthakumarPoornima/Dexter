from __future__ import annotations

from backend.jobs.models import ApplicationProfile


SENSITIVE_KINDS = {"work_authorization", "sponsorship", "demographic", "race", "gender", "veteran", "disability"}


def planned_field_values(fields: list[dict], profile: ApplicationProfile) -> tuple[list[dict], list[dict]]:
    filled = []
    blocked = []
    safe_values = {
        "name": profile.name,
        "email": profile.email,
        "phone": profile.phone,
        "location": profile.location,
        "linkedin": profile.linkedin_url,
        "github": profile.github_url,
        "portfolio": profile.portfolio_url,
        "resume": profile.resume_path,
    }
    for field in fields:
        kind = field.get("kind", "unknown")
        if kind in SENSITIVE_KINDS or kind == "unknown":
            blocked.append({**field, "reason": "requires_human_review"})
        elif safe_values.get(kind):
            filled.append({**field, "value": safe_values[kind]})
        else:
            blocked.append({**field, "reason": "missing_profile_value"})
    return filled, blocked
