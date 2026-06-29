from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path

from backend.jobs.adapters.base import JobCreate
from backend.jobs.config import raw_payloads_dir
from backend.jobs.dedupe import canonical_job_key


def split_bullets(text: str, keywords: tuple[str, ...]) -> list[str]:
    lines = []
    for raw in re.split(r"[\n\r]|(?:\.\s+)", text or ""):
        clean = re.sub(r"\s+", " ", raw).strip(" -:*")
        if len(clean) > 8 and any(keyword in clean.lower() for keyword in keywords):
            lines.append(clean[:400])
    return lines[:12]


def enrich_job(job: JobCreate) -> JobCreate:
    text = job.description or ""
    if not job.requirements:
        job.requirements = split_bullets(text, ("require", "experience", "skill", "must", "proficient", "degree"))
    if not job.responsibilities:
        job.responsibilities = split_bullets(text, ("build", "design", "develop", "work", "support", "collaborate"))
    if not job.benefits:
        job.benefits = split_bullets(text, ("benefit", "salary", "equity", "health", "remote", "pto"))
    if not job.employment_type or job.employment_type == "unknown":
        blob = f"{job.title} {job.description}".lower()
        job.employment_type = "internship" if "intern" in blob else "full_time"
    job.internship_flag = job.internship_flag or job.employment_type == "internship"
    return job


def write_raw_payload(source: str, canonical_id: str, raw: dict) -> Path:
    target_dir = raw_payloads_dir() / source
    target_dir.mkdir(parents=True, exist_ok=True)
    payload_text = json.dumps(raw, sort_keys=True, indent=2, default=str)
    digest = sha256(payload_text.encode("utf-8")).hexdigest()[:16]
    path = target_dir / f"{canonical_id}_{digest}.json"
    path.write_text(payload_text, encoding="utf-8")
    return path


def prepare_job(job: JobCreate) -> tuple[JobCreate, str, Path]:
    enriched = enrich_job(job)
    canonical_id = canonical_job_key(enriched)
    raw_path = write_raw_payload(enriched.source, canonical_id, enriched.raw)
    return enriched, canonical_id, raw_path
