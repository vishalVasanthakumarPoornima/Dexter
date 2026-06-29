from __future__ import annotations

from backend.jobs.service import latest_report


def send_local_report() -> dict:
    report = latest_report()
    return {"ok": bool(report.get("ok")), "mode": "local_report", "report": report}
