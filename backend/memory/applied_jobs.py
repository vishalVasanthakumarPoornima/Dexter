from __future__ import annotations

from backend.jobs.service import list_jobs


def applied_job_summary() -> dict:
    return list_jobs(status="submitted")
