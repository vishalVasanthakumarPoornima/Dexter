from __future__ import annotations


def send_jobs_whatsapp_report(*_args, **_kwargs) -> dict:
    return {
        "ok": False,
        "mode": "not_configured",
        "message": "WhatsApp provider is not configured. Use the local markdown report fallback.",
    }
