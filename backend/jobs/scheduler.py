from __future__ import annotations

from backend.jobs.service import run_daily


def run_scheduled_jobs_demo() -> dict:
    return run_daily(demo=True)
