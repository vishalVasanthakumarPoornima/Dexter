from __future__ import annotations


def send_jobs_email_report(*_args, **_kwargs) -> dict:
    return {
        "ok": False,
        "mode": "not_configured",
        "message": "Email provider is not configured. Use the local markdown report fallback.",
    }
