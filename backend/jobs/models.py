from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class JobSource(Base):
    __tablename__ = "job_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(80), default="adapter")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    requires_api_key: Mapped[bool] = mapped_column(Boolean, default=False)
    restricted_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    health_status: Mapped[str] = mapped_column(String(80), default="unknown")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("canonical_id", name="uq_jobs_canonical_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_id: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    company: Mapped[str] = mapped_column(String(220), index=True)
    location: Mapped[str] = mapped_column(String(220), default="")
    remote_type: Mapped[str] = mapped_column(String(80), default="unknown")
    employment_type: Mapped[str] = mapped_column(String(80), default="unknown")
    internship_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    seniority: Mapped[str] = mapped_column(String(80), default="")
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(16), default="USD")
    description: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    responsibilities: Mapped[list] = mapped_column(JSON, default=list)
    benefits: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(120), index=True)
    source_job_id: Mapped[str] = mapped_column(String(220), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    apply_url: Mapped[str] = mapped_column(Text, default="")
    date_posted: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.0)
    raw_payload_path: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(80), default="new")
    restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_required: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    scores: Mapped[list["JobScore"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    packets: Mapped[list["ApplicationPacket"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobSnapshot(Base):
    __tablename__ = "job_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(120), index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    hash: Mapped[str] = mapped_column(String(80), index=True)


class ApplicationProfile(Base):
    __tablename__ = "application_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), default="Default")
    email: Mapped[str] = mapped_column(String(220), default="")
    phone: Mapped[str] = mapped_column(String(80), default="")
    location: Mapped[str] = mapped_column(String(220), default="")
    work_authorization: Mapped[str] = mapped_column(String(220), default="")
    visa_notes: Mapped[str] = mapped_column(Text, default="")
    github_url: Mapped[str] = mapped_column(Text, default="")
    linkedin_url: Mapped[str] = mapped_column(Text, default="")
    portfolio_url: Mapped[str] = mapped_column(Text, default="")
    preferred_roles: Mapped[list] = mapped_column(JSON, default=list)
    preferred_locations: Mapped[list] = mapped_column(JSON, default=list)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    resume_path: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("application_profiles.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(Text)
    parsed_text: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[list] = mapped_column(JSON, default=list)
    projects: Mapped[list] = mapped_column(JSON, default=list)
    experience: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class JobScore(Base):
    __tablename__ = "job_scores"
    __table_args__ = (UniqueConstraint("job_id", "profile_id", name="uq_job_score_profile"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("application_profiles.id", ondelete="CASCADE"), index=True)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    title_score: Mapped[float] = mapped_column(Float, default=0.0)
    skills_score: Mapped[float] = mapped_column(Float, default=0.0)
    seniority_score: Mapped[float] = mapped_column(Float, default=0.0)
    location_score: Mapped[float] = mapped_column(Float, default=0.0)
    visa_score: Mapped[float] = mapped_column(Float, default=0.0)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.0)
    source_confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    explanation: Mapped[str] = mapped_column(Text, default="")
    gaps: Mapped[list] = mapped_column(JSON, default=list)
    match_reasons: Mapped[list] = mapped_column(JSON, default=list)
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[str] = mapped_column(String(80), default="manual_review")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    job: Mapped[Job] = relationship(back_populates="scores")


class ApplicationPacket(Base):
    __tablename__ = "application_packets"
    __table_args__ = (UniqueConstraint("job_id", "profile_id", name="uq_packet_job_profile"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("application_profiles.id", ondelete="CASCADE"), index=True)
    resume_variant_path: Mapped[str] = mapped_column(Text, default="")
    cover_letter_path: Mapped[str] = mapped_column(Text, default="")
    short_answers_json: Mapped[dict] = mapped_column(JSON, default=dict)
    resume_diff_summary: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(String(80), default="manual_review")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    blockers: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    job: Mapped[Job] = relationship(back_populates="packets")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="packet", cascade="all, delete-orphan")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_packet_id: Mapped[int] = mapped_column(ForeignKey("application_packets.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(80), default="requested")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    packet: Mapped[ApplicationPacket] = relationship(back_populates="approvals")


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    packet_id: Mapped[int | None] = mapped_column(ForeignKey("application_packets.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(80), default="drafted")
    source: Mapped[str] = mapped_column(String(120), default="")
    apply_url: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_text: Mapped[str] = mapped_column(Text, default="")
    confirmation_screenshot: Mapped[str] = mapped_column(Text, default="")
    failure_reason: Mapped[str] = mapped_column(Text, default="")
    manual_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(120), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(80), default="running")
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_new: Mapped[int] = mapped_column(Integer, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0)
    jobs_deduped: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class BrowserApplySession(Base):
    __tablename__ = "browser_apply_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(80), default="created")
    url: Mapped[str] = mapped_column(Text, default="")
    screenshot_dir: Mapped[str] = mapped_column(Text, default="")
    fields_detected: Mapped[list] = mapped_column(JSON, default=list)
    fields_filled: Mapped[list] = mapped_column(JSON, default=list)
    fields_blocked: Mapped[list] = mapped_column(JSON, default=list)
    requires_human: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
