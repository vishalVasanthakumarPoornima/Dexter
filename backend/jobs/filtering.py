from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from backend.jobs.schemas import JobQuery


ROLE_ALIASES: dict[str, set[str]] = {
    "software": {"software", "swe", "developer", "development", "programmer", "full stack", "full-stack"},
    "backend": {"backend", "back end", "api", "server", "platform", "infrastructure", "distributed"},
    "frontend": {"frontend", "front end", "front-end", "react", "web", "ui", "javascript", "typescript"},
    "ai": {"ai", "ml", "machine learning", "llm", "model", "agent", "data science"},
    "security": {"security", "cyber", "cybersecurity", "appsec", "application security"},
    "data": {"data engineer", "analytics engineer", "data platform", "etl", "warehouse"},
}

INTERNSHIP_TERMS = {"intern", "internship", "co-op", "coop", "university", "student"}
NEW_GRAD_TERMS = {"new grad", "new graduate", "early career", "entry level", "university grad"}
UNRELATED_TITLE_TERMS = {
    "account manager",
    "brand manager",
    "customer support",
    "environmental",
    "field sales",
    "jefe",
    "mechanical",
    "product manager",
    "sales",
    "safety coordinator",
    "store manager",
    "supervisor",
}


def _value(item: Any, name: str, default: Any = "") -> Any:
    return getattr(item, name, default)


def _list_value(item: Any, name: str) -> list[str]:
    value = _value(item, name, [])
    return value if isinstance(value, list) else []


def job_search_blob(item: Any) -> str:
    parts = [
        _value(item, "title"),
        _value(item, "company"),
        _value(item, "location"),
        _value(item, "remote_type"),
        _value(item, "employment_type"),
        _value(item, "description"),
        " ".join(str(v) for v in _list_value(item, "requirements")),
        " ".join(str(v) for v in _list_value(item, "responsibilities")),
        _value(item, "source_url"),
        _value(item, "apply_url"),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]+", (text or "").lower()))


def _contains_any(blob: str, terms: set[str]) -> bool:
    return any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", blob) for term in terms)


def _has_internship_signal(item: Any, blob: str, *, title_only: bool = False) -> bool:
    title = str(_value(item, "title")).lower()
    employment_type = str(_value(item, "employment_type")).lower()
    text = title if title_only else f"{title} {employment_type} {blob}"
    return bool(re.search(r"\b(intern|internship|co-op|coop|student)\b", text)) or "university grad" in text


def _has_new_grad_signal(item: Any, blob: str) -> bool:
    employment_type = str(_value(item, "employment_type")).lower()
    text = f"{_value(item, 'title')} {employment_type} {blob}".lower()
    return "new_grad" in employment_type or _contains_any(text, NEW_GRAD_TERMS)


def _role_matches(role: str, item: Any, blob: str) -> bool:
    role_lower = role.lower().strip()
    title = str(_value(item, "title")).lower()
    internship_role = "intern" in role_lower or "internship" in role_lower
    new_grad_role = "new grad" in role_lower or "new graduate" in role_lower
    if not role_lower:
        return True

    if any(term in title for term in UNRELATED_TITLE_TERMS):
        return False

    if internship_role and not _has_internship_signal(item, blob, title_only=True):
        return False
    if new_grad_role and not _has_new_grad_signal(item, blob):
        return False

    if "software" in role_lower or "swe" in role_lower:
        return _contains_any(
            title,
            {
                "software",
                "swe",
                "development engineer",
                "full stack",
                "full-stack",
                "backend engineer",
                "front end engineer",
                "front-end engineer",
                "frontend engineer",
            },
        )
    if "backend" in role_lower:
        return _contains_any(title, {"backend", "back end", "api engineer", "platform engineer", "server engineer", "software"})
    if "frontend" in role_lower or "front-end" in role_lower:
        return _contains_any(title, {"frontend", "front end", "front-end", "react", "web engineer", "ui engineer", "software"})
    if "full stack" in role_lower or "full-stack" in role_lower:
        return _contains_any(title, {"full stack", "full-stack", "software", "developer"})
    if "ai" in role_lower or "machine learning" in role_lower or "ml" in role_lower:
        return _contains_any(title, {"ai", "ml", "machine learning", "applied scientist", "data scientist", "software"})
    if "security" in role_lower or "cyber" in role_lower:
        return _contains_any(title, {"security", "cyber", "appsec", "application security"})
    if "data" in role_lower:
        return _contains_any(title, ROLE_ALIASES["data"] | {"analytics engineer"})

    role_tokens = _tokens(role_lower) - {"engineer", "engineering", "intern", "internship", "new", "grad"}
    blob_tokens = _tokens(blob)
    return not role_tokens or bool(role_tokens & blob_tokens)


def _employment_matches(item: Any, query: JobQuery, blob: str) -> bool:
    employment_types = {value.lower() for value in query.employment_types if value}
    employment_type = str(_value(item, "employment_type")).lower()
    internship_like = _has_internship_signal(item, blob)
    new_grad_like = _has_new_grad_signal(item, blob)

    if query.require_internship and not internship_like:
        return False

    if not employment_types:
        return True
    if "internship" in employment_types and internship_like and not new_grad_like:
        return True
    if "new_grad" in employment_types and new_grad_like:
        return True
    if employment_type in employment_types:
        return True
    return False


def _work_mode_matches(item: Any, query: JobQuery) -> bool:
    remote_type = str(_value(item, "remote_type")).lower()
    if "remote" in remote_type:
        return query.include_remote
    if "hybrid" in remote_type:
        return query.include_hybrid
    if "onsite" in remote_type:
        return query.include_onsite
    return query.include_remote or query.include_hybrid or query.include_onsite


def _posted_recently(item: Any, query: JobQuery) -> bool:
    if not query.posted_within_days:
        return True
    posted = _value(item, "date_posted", None)
    if not posted:
        return False
    posted_dt = posted if posted.tzinfo else posted.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - posted_dt).days
    return 0 <= age_days <= query.posted_within_days


def _term_matches(query: JobQuery, blob: str) -> bool:
    season = query.season.lower().strip()
    if season and season not in {"any", "all"} and season not in blob:
        return False
    if query.cohort_year and str(query.cohort_year) not in blob:
        return False
    return True


def _keyword_matches(query: JobQuery, blob: str) -> bool:
    keyword = query.keywords.lower().strip()
    if not keyword:
        return True
    tokens = _tokens(keyword) - {"and", "or", "the", "for", "jobs", "job"}
    if not tokens:
        return True
    return any(token in blob for token in tokens)


def matches_job_query(item: Any, query: JobQuery | None) -> bool:
    if query is None or query.demo:
        return True

    blob = job_search_blob(item)
    roles = [role for role in query.roles if role.strip()] or ([query.keywords] if query.keywords.strip() else [])

    if roles and not any(_role_matches(role, item, blob) for role in roles):
        return False
    if not _keyword_matches(query, blob):
        return False
    if not _employment_matches(item, query, blob):
        return False
    if not _work_mode_matches(item, query):
        return False
    if not _posted_recently(item, query):
        return False
    if not _term_matches(query, blob):
        return False

    location = query.location.lower().strip()
    if location and location not in blob:
        return False
    return True
