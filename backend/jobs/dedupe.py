from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse, urlunparse

from backend.jobs.adapters.base import JobCreate


TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "gh_src", "lever-source"}


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+$", "", parsed.path)
    return urlunparse((parsed.scheme.lower() or "https", host, path, "", "", ""))


def normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def canonical_job_key(job: JobCreate) -> str:
    preferred_url = normalize_url(job.apply_url or job.source_url)
    if preferred_url and not preferred_url.startswith("fixture://"):
        raw = f"url:{preferred_url}"
    else:
        raw = "|".join(
            [
                normalize_token(job.company),
                normalize_token(job.title),
                normalize_token(job.location),
                normalize_token(job.source_job_id),
            ]
        )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def duplicate_confidence(left: JobCreate, right: JobCreate) -> float:
    if normalize_url(left.apply_url) and normalize_url(left.apply_url) == normalize_url(right.apply_url):
        return 0.98
    score = 0.0
    if normalize_token(left.company) == normalize_token(right.company):
        score += 0.35
    if normalize_token(left.title) == normalize_token(right.title):
        score += 0.35
    if normalize_token(left.location) == normalize_token(right.location):
        score += 0.15
    if left.source_job_id and left.source_job_id == right.source_job_id:
        score += 0.15
    return min(score, 1.0)
