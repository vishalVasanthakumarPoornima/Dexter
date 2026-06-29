from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from backend.jobs.models import ApplicationProfile, Job


AI_TERMS = {"ai", "ml", "machine learning", "llm", "rag", "agent", "model"}
SECURITY_TERMS = {"security", "cybersecurity", "threat", "red team", "appsec"}
BACKEND_TERMS = {"backend", "api", "python", "fastapi", "sql", "database", "distributed"}
FRONTEND_TERMS = {"frontend", "react", "typescript", "javascript", "ui"}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]+", (text or "").lower()))


def _contains_any(blob: str, terms: set[str]) -> bool:
    lower = blob.lower()
    return any(term in lower for term in terms)


def score_job(job: Job, profile: ApplicationProfile) -> dict:
    blob = f"{job.title} {job.description} {' '.join(job.requirements or [])}".lower()
    title_tokens = _tokens(job.title)
    target_tokens = _tokens(" ".join(profile.preferred_roles or []))
    skill_tokens = _tokens(" ".join(profile.skills or []))
    job_tokens = _tokens(blob)

    title_overlap = len(title_tokens & target_tokens) / max(len(title_tokens | target_tokens), 1)
    skills_overlap = len(skill_tokens & job_tokens) / max(min(len(skill_tokens), 12), 1)
    location_blob = f"{job.location} {job.remote_type}".lower()
    preferred_locations = " ".join(profile.preferred_locations or []).lower()
    location_score = 1.0 if "remote" in location_blob and "remote" in preferred_locations else 0.65
    if profile.location and profile.location.lower() in location_blob:
        location_score = 1.0

    seniority_score = 0.6
    if "senior" in blob and "intern" in " ".join(profile.preferred_roles or []).lower():
        seniority_score = 0.2
    elif job.internship_flag or "new_grad" in job.employment_type:
        seniority_score = 1.0

    visa_score = 0.7
    if "sponsor" in blob or "authorization" in blob:
        visa_score = 0.55 if not profile.work_authorization else 0.8

    freshness_score = job.freshness_score or 0.5
    if job.date_posted:
        posted = job.date_posted if job.date_posted.tzinfo else job.date_posted.replace(tzinfo=timezone.utc)
        age_days = max((datetime.now(timezone.utc) - posted).days, 0)
        freshness_score = max(0.1, math.exp(-age_days / 30))

    source_confidence = {
        "greenhouse": 0.9,
        "lever": 0.9,
        "usajobs": 0.95,
        "adzuna": 0.75,
        "remotive": 0.8,
        "github_lists": 0.7,
        "rss": 0.6,
        "manual_link": 0.5,
        "restricted_manual": 0.4,
    }.get(job.source, 0.55)

    domain_bonus = 0.0
    reasons = []
    if _contains_any(blob, AI_TERMS):
        domain_bonus += 0.08
        reasons.append("AI/ML relevance")
    if _contains_any(blob, SECURITY_TERMS):
        domain_bonus += 0.08
        reasons.append("security relevance")
    if _contains_any(blob, BACKEND_TERMS):
        domain_bonus += 0.06
        reasons.append("backend/API relevance")
    if _contains_any(blob, FRONTEND_TERMS):
        domain_bonus += 0.04
        reasons.append("frontend relevance")

    weighted = (
        title_overlap * 22
        + min(skills_overlap, 1.0) * 28
        + seniority_score * 15
        + location_score * 10
        + visa_score * 8
        + freshness_score * 9
        + source_confidence * 8
        + domain_bonus * 100
    )
    overall = max(0, min(100, round(weighted, 1)))
    gaps = []
    if skills_overlap < 0.25:
        gaps.append("Low explicit skill overlap; review description before applying.")
    if seniority_score < 0.5:
        gaps.append("Seniority may not fit current target roles.")
    if job.manual_required:
        gaps.append("Manual or supervised application required.")
    risk_flags = []
    if job.restricted:
        risk_flags.append("restricted_source_manual_only")
    if not job.description:
        risk_flags.append("missing_description")
    recommendation = "apply" if overall >= 72 and not job.restricted else "maybe"
    if overall < 45:
        recommendation = "skip"
    if job.restricted or job.manual_required:
        recommendation = "manual_review" if overall >= 45 else recommendation
    if title_overlap > 0:
        reasons.append("title matches target role family")
    if skills_overlap > 0:
        reasons.append("resume/profile skills overlap with posting")
    if location_score >= 1:
        reasons.append("location or remote fit")

    return {
        "overall_score": overall,
        "title_score": round(title_overlap * 100, 1),
        "skills_score": round(min(skills_overlap, 1.0) * 100, 1),
        "seniority_score": round(seniority_score * 100, 1),
        "location_score": round(location_score * 100, 1),
        "visa_score": round(visa_score * 100, 1),
        "freshness_score": round(freshness_score * 100, 1),
        "source_confidence_score": round(source_confidence * 100, 1),
        "explanation": f"Score {overall}/100 from role, skills, seniority, location, freshness, and source confidence.",
        "gaps": gaps,
        "match_reasons": reasons[:8],
        "risk_flags": risk_flags,
        "recommendation": recommendation,
        "confidence": round(0.55 + source_confidence * 0.3, 2),
    }
