from __future__ import annotations

from backend.jobs.models import ApplicationEvent


def record_event(session, event_type: str, message: str, application_id: int | None = None, metadata: dict | None = None) -> ApplicationEvent:
    event = ApplicationEvent(
        application_id=application_id,
        event_type=event_type,
        message=message,
        metadata_json=metadata or {},
    )
    session.add(event)
    session.flush()
    return event
