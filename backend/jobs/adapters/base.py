from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from backend.jobs.schemas import JobQuery


@dataclass(slots=True)
class SourceHealth:
    ok: bool
    status: str
    message: str = ""
    requires_api_key: bool = False
    restricted_mode: bool = False


@dataclass(slots=True)
class RawJob:
    source: str
    payload: dict[str, Any]
    source_url: str = ""
    fetched_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class JobCreate:
    title: str
    company: str
    location: str = ""
    remote_type: str = "unknown"
    employment_type: str = "unknown"
    internship_flag: bool = False
    seniority: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str = "USD"
    description: str = ""
    requirements: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    source: str = ""
    source_job_id: str = ""
    source_url: str = ""
    apply_url: str = ""
    date_posted: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    restricted: bool = False
    manual_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class JobSourceAdapter(Protocol):
    name: str
    source_type: str

    def validate_config(self) -> SourceHealth:
        ...

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        ...

    def normalize(self, raw: RawJob) -> JobCreate:
        ...

    def supports_apply(self) -> bool:
        ...
