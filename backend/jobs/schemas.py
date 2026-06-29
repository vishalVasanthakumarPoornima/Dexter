from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobQuery(BaseModel):
    keywords: str = ""
    location: str = ""
    remote: bool | None = None
    employment_types: list[str] = Field(default_factory=list)
    max_results: int = 100
    demo: bool = False


class ManualLinkRequest(BaseModel):
    url: str
    title: str = ""
    company: str = ""
    notes: str = ""


class IngestRequest(BaseModel):
    source: str = "all"
    query: JobQuery = Field(default_factory=JobQuery)
    demo: bool = False
    dry_run: bool = False


class PacketRequest(BaseModel):
    profile_id: int | None = None
    force: bool = False


class ApprovalRequest(BaseModel):
    notes: str = ""


class SourceUpdateRequest(BaseModel):
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class JobResponse(BaseModel):
    id: int
    title: str
    company: str
    location: str = ""
    source: str
    apply_url: str = ""
    source_url: str = ""
    status: str
    overall_score: float | None = None
    recommendation: str | None = None
    discovered_at: datetime | None = None
