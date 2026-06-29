from __future__ import annotations

from pathlib import Path

from backend.jobs.browser.form_analyzer import analyze_form_file
from backend.jobs.browser.form_filler import planned_field_values
from backend.jobs.config import PROJECT_ROOT, screenshots_dir
from backend.jobs.models import ApplicationProfile, BrowserApplySession, Job


def demo_form_path() -> Path:
    return PROJECT_ROOT / "tests" / "fixtures" / "jobs" / "sample_application_form.html"


def create_apply_session(session, job: Job, profile: ApplicationProfile, demo: bool = False) -> BrowserApplySession:
    url = str(demo_form_path()) if demo else job.apply_url
    shot_dir = screenshots_dir() / f"job_{job.id}"
    shot_dir.mkdir(parents=True, exist_ok=True)
    fields = analyze_form_file(url) if demo or Path(url).exists() else []
    filled, blocked = planned_field_values(fields, profile)
    status = "requires_human" if blocked else "filled_review_required"

    screenshot_path = shot_dir / "summary.txt"
    screenshot_path.write_text(
        "Dexter supervised apply session placeholder.\n"
        "Final submit was not clicked.\n"
        f"Fields detected: {len(fields)}\n"
        f"Fields filled: {len(filled)}\n"
        f"Fields blocked: {len(blocked)}\n",
        encoding="utf-8",
    )

    browser_session = BrowserApplySession(
        job_id=job.id,
        status=status,
        url=Path(url).resolve().as_uri() if Path(url).exists() else url,
        screenshot_dir=str(shot_dir),
        fields_detected=fields,
        fields_filled=filled,
        fields_blocked=blocked,
        requires_human=True,
        metadata_json={"final_submit_clicked": False, "demo": demo},
    )
    session.add(browser_session)
    session.flush()
    return browser_session
