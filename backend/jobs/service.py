from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.jobs.adapters.base import JobCreate
from backend.jobs.application_packets import upsert_packet
from backend.jobs.approvals import approve_packet, ensure_approval, reject_packet
from backend.jobs.browser.apply_session import create_apply_session
from backend.jobs.config import load_jobs_config
from backend.jobs.db import get_session, init_db
from backend.jobs.models import (
    Approval,
    ApplicationProfile,
    BrowserApplySession,
    IngestionRun,
    Job,
    JobScore,
    JobSnapshot,
    JobSource,
    utc_now,
)
from backend.jobs.normalization import prepare_job
from backend.jobs.reports import generate_daily_report
from backend.jobs.schemas import JobQuery
from backend.jobs.scoring import score_job
from backend.jobs.source_registry import build_adapters
from backend.profile.profile_service import get_or_create_default_profile
from backend.utils.logger import log_action


DEMO_SOURCES = ["greenhouse", "lever", "remotive", "github_lists", "rss", "usajobs", "adzuna", "company_careers"]


def _session_or_new(session: Session | None = None) -> tuple[Session, bool]:
    if session is not None:
        return session, False
    return get_session(), True


def _serialize_dt(value) -> str | None:
    return value.isoformat() if value else None


def ensure_job_sources(session: Session, config: dict | None = None) -> list[JobSource]:
    cfg = config or load_jobs_config()
    sources = []
    for name, adapter in build_adapters(cfg, include_disabled=True).items():
        health = adapter.validate_config()
        source_cfg = cfg.get("sources", {}).get(name, {})
        source = session.execute(select(JobSource).where(JobSource.name == name)).scalar_one_or_none()
        if source is None:
            source = JobSource(name=name)
            session.add(source)
        source.type = getattr(adapter, "source_type", "adapter")
        source.enabled = bool(source_cfg.get("enabled", True))
        source.requires_api_key = health.requires_api_key
        source.restricted_mode = health.restricted_mode
        source.health_status = health.status
        source.last_error = "" if health.ok else health.message
        source.metadata_json = {"message": health.message, **source_cfg}
        sources.append(source)
    session.flush()
    return sources


def _upsert_job(session: Session, job_create: JobCreate) -> tuple[Job, bool, bool]:
    prepared, canonical_id, raw_path = prepare_job(job_create)
    existing = session.execute(select(Job).where(Job.canonical_id == canonical_id)).scalar_one_or_none()
    is_new = existing is None
    is_updated = False
    if existing is None:
        existing = Job(canonical_id=canonical_id, title=prepared.title, company=prepared.company, source=prepared.source)
        session.add(existing)
    else:
        is_updated = True

    for key in (
        "title",
        "company",
        "location",
        "remote_type",
        "employment_type",
        "internship_flag",
        "seniority",
        "salary_min",
        "salary_max",
        "currency",
        "description",
        "requirements",
        "responsibilities",
        "benefits",
        "source",
        "source_job_id",
        "source_url",
        "apply_url",
        "date_posted",
        "restricted",
        "manual_required",
    ):
        setattr(existing, key, getattr(prepared, key))
    existing.raw_payload_path = str(raw_path)
    existing.freshness_score = 1.0 if prepared.date_posted else 0.5
    existing.status = existing.status or "new"
    existing.metadata_json = prepared.metadata or {}
    session.flush()
    session.add(
        JobSnapshot(
            job_id=existing.id,
            source=existing.source,
            raw_payload=prepared.raw,
            hash=canonical_id,
        )
    )
    return existing, is_new, is_updated


def ingest_jobs(
    source: str = "all",
    query: JobQuery | None = None,
    demo: bool = False,
    dry_run: bool = False,
    session: Session | None = None,
) -> dict[str, Any]:
    active_session, should_close = _session_or_new(session)
    try:
        init_db()
        cfg = load_jobs_config()
        ensure_job_sources(active_session, cfg)
        job_query = query or JobQuery()
        job_query.demo = bool(demo or job_query.demo)
        if not job_query.max_results:
            job_query.max_results = int(cfg.get("limits", {}).get("max_jobs_per_source", 100))

        adapters = build_adapters(cfg, include_disabled=job_query.demo)
        if source != "all":
            adapters = {name: adapter for name, adapter in adapters.items() if name == source}
        elif job_query.demo:
            adapters = {name: adapter for name, adapter in adapters.items() if name in DEMO_SOURCES}

        source_results = []
        total_found = total_new = total_updated = total_deduped = 0
        for name, adapter in adapters.items():
            run = IngestionRun(source=name, status="running")
            active_session.add(run)
            active_session.flush()
            try:
                raw_jobs = adapter.fetch_jobs(job_query)
                seen_canonicals = set()
                new_count = updated_count = deduped_count = 0
                normalized_preview = []
                for raw in raw_jobs:
                    normalized = adapter.normalize(raw)
                    prepared, canonical_id, _ = prepare_job(normalized) if dry_run else (normalized, "", None)
                    if dry_run:
                        if canonical_id in seen_canonicals:
                            deduped_count += 1
                            continue
                        seen_canonicals.add(canonical_id)
                        normalized_preview.append({"title": prepared.title, "company": prepared.company, "source": prepared.source})
                        continue
                    job, is_new, is_updated = _upsert_job(active_session, normalized)
                    if job.canonical_id in seen_canonicals:
                        deduped_count += 1
                    seen_canonicals.add(job.canonical_id)
                    if is_new:
                        new_count += 1
                    elif is_updated:
                        updated_count += 1
                run.status = "success"
                run.jobs_found = len(raw_jobs)
                run.jobs_new = new_count
                run.jobs_updated = updated_count
                run.jobs_deduped = deduped_count
                run.finished_at = utc_now()
                run.metadata_json = {"dry_run": dry_run, "preview": normalized_preview[:10]}
                source_row = active_session.execute(select(JobSource).where(JobSource.name == name)).scalar_one_or_none()
                if source_row:
                    source_row.health_status = "ok"
                    source_row.last_run_at = utc_now()
                    source_row.last_error = ""
                total_found += len(raw_jobs)
                total_new += new_count
                total_updated += updated_count
                total_deduped += deduped_count
                source_results.append(
                    {
                        "source": name,
                        "status": "success",
                        "jobs_found": len(raw_jobs),
                        "jobs_new": new_count,
                        "jobs_updated": updated_count,
                        "jobs_deduped": deduped_count,
                    }
                )
            except Exception as exc:
                run.status = "failed"
                run.finished_at = utc_now()
                run.error = str(exc)
                source_row = active_session.execute(select(JobSource).where(JobSource.name == name)).scalar_one_or_none()
                if source_row:
                    source_row.health_status = "error"
                    source_row.last_error = str(exc)
                source_results.append({"source": name, "status": "failed", "error": str(exc)})

        if not dry_run:
            active_session.commit()
        log_action("jobs_ingest", {"source": source, "demo": demo, "dry_run": dry_run, "results": source_results})
        return {
            "ok": True,
            "source": source,
            "demo": demo,
            "dry_run": dry_run,
            "jobs_found": total_found,
            "jobs_new": total_new,
            "jobs_updated": total_updated,
            "jobs_deduped": total_deduped,
            "sources": source_results,
        }
    finally:
        if should_close:
            active_session.close()


def score_jobs(profile_id: int | None = None, session: Session | None = None) -> dict[str, Any]:
    active_session, should_close = _session_or_new(session)
    try:
        init_db()
        profile = active_session.get(ApplicationProfile, profile_id) if profile_id else get_or_create_default_profile(active_session)
        scored = 0
        for job in active_session.execute(select(Job)).scalars().all():
            payload = score_job(job, profile)
            existing = (
                active_session.query(JobScore)
                .filter(JobScore.job_id == job.id, JobScore.profile_id == profile.id)
                .one_or_none()
            )
            if existing is None:
                existing = JobScore(job_id=job.id, profile_id=profile.id)
                active_session.add(existing)
            for key, value in payload.items():
                setattr(existing, key, value)
            scored += 1
        active_session.commit()
        return {"ok": True, "profile_id": profile.id, "jobs_scored": scored}
    finally:
        if should_close:
            active_session.close()


def generate_packets(
    profile_id: int | None = None,
    limit: int | None = None,
    min_score: float = 55.0,
    session: Session | None = None,
) -> dict[str, Any]:
    active_session, should_close = _session_or_new(session)
    try:
        init_db()
        profile = active_session.get(ApplicationProfile, profile_id) if profile_id else get_or_create_default_profile(active_session)
        scores = (
            active_session.query(JobScore)
            .filter(JobScore.profile_id == profile.id, JobScore.overall_score >= min_score)
            .order_by(desc(JobScore.overall_score))
            .limit(limit or load_jobs_config().get("limits", {}).get("max_application_packets_per_run", 10))
            .all()
        )
        packets = []
        for score in scores:
            job = active_session.get(Job, score.job_id)
            if not job:
                continue
            packet = upsert_packet(active_session, job, profile, score)
            approval = ensure_approval(active_session, packet)
            packets.append({"packet_id": packet.id, "job_id": job.id, "approval_id": approval.id, "recommendation": packet.recommendation})
        active_session.commit()
        return {"ok": True, "profile_id": profile.id, "packets_generated": len(packets), "packets": packets}
    finally:
        if should_close:
            active_session.close()


def generate_packet_for_job(job_id: int, profile_id: int | None = None, session: Session | None = None) -> dict[str, Any]:
    active_session, should_close = _session_or_new(session)
    try:
        profile = active_session.get(ApplicationProfile, profile_id) if profile_id else get_or_create_default_profile(active_session)
        job = active_session.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": f"Unknown job id: {job_id}"}
        score = (
            active_session.query(JobScore)
            .filter(JobScore.job_id == job.id, JobScore.profile_id == profile.id)
            .one_or_none()
        )
        packet = upsert_packet(active_session, job, profile, score)
        approval = ensure_approval(active_session, packet)
        active_session.commit()
        return {"ok": True, "packet": serialize_packet(packet, approval)}
    finally:
        if should_close:
            active_session.close()


def run_daily(demo: bool = False) -> dict[str, Any]:
    ingest = ingest_jobs(source="all", query=JobQuery(keywords="Software Engineer Intern 2027", demo=demo), demo=demo)
    scoring = score_jobs()
    packets = generate_packets()
    with get_session() as session:
        report = generate_daily_report(session)
        session.commit()
    return {"ok": True, "ingest": ingest, "scoring": scoring, "packets": packets, "report": report}


def serialize_score(score: JobScore | None) -> dict | None:
    if score is None:
        return None
    return {
        "id": score.id,
        "overall_score": score.overall_score,
        "title_score": score.title_score,
        "skills_score": score.skills_score,
        "seniority_score": score.seniority_score,
        "location_score": score.location_score,
        "visa_score": score.visa_score,
        "freshness_score": score.freshness_score,
        "source_confidence_score": score.source_confidence_score,
        "explanation": score.explanation,
        "gaps": score.gaps,
        "match_reasons": score.match_reasons,
        "risk_flags": score.risk_flags,
        "recommendation": score.recommendation,
        "confidence": score.confidence,
        "created_at": _serialize_dt(score.created_at),
    }


def serialize_packet(packet, approval: Approval | None = None) -> dict:
    return {
        "id": packet.id,
        "job_id": packet.job_id,
        "profile_id": packet.profile_id,
        "resume_variant_path": packet.resume_variant_path,
        "cover_letter_path": packet.cover_letter_path,
        "short_answers_json": packet.short_answers_json,
        "resume_diff_summary": packet.resume_diff_summary,
        "recommendation": packet.recommendation,
        "confidence": packet.confidence,
        "blockers": packet.blockers,
        "created_at": _serialize_dt(packet.created_at),
        "approval": serialize_approval(approval or (packet.approvals[-1] if packet.approvals else None)),
    }


def serialize_approval(approval: Approval | None) -> dict | None:
    if approval is None:
        return None
    return {
        "id": approval.id,
        "application_packet_id": approval.application_packet_id,
        "status": approval.status,
        "requested_at": _serialize_dt(approval.requested_at),
        "approved_at": _serialize_dt(approval.approved_at),
        "rejected_at": _serialize_dt(approval.rejected_at),
        "notes": approval.notes,
    }


def serialize_job(job: Job, score: JobScore | None = None, include_detail: bool = False) -> dict:
    payload = {
        "id": job.id,
        "canonical_id": job.canonical_id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote_type": job.remote_type,
        "employment_type": job.employment_type,
        "internship_flag": job.internship_flag,
        "seniority": job.seniority,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "currency": job.currency,
        "source": job.source,
        "source_job_id": job.source_job_id,
        "source_url": job.source_url,
        "apply_url": job.apply_url,
        "date_posted": _serialize_dt(job.date_posted),
        "discovered_at": _serialize_dt(job.discovered_at),
        "freshness_score": job.freshness_score,
        "raw_payload_path": job.raw_payload_path,
        "status": job.status,
        "restricted": job.restricted,
        "manual_required": job.manual_required,
        "score": serialize_score(score),
    }
    if include_detail:
        packet = job.packets[-1] if job.packets else None
        payload.update(
            {
                "description": job.description,
                "requirements": job.requirements,
                "responsibilities": job.responsibilities,
                "benefits": job.benefits,
                "metadata": job.metadata_json,
                "packet": serialize_packet(packet) if packet else None,
            }
        )
    return payload


def list_jobs(
    status: str | None = None,
    source: str | None = None,
    q: str | None = None,
    min_score: float | None = None,
    limit: int = 100,
    session: Session | None = None,
) -> dict[str, Any]:
    active_session, should_close = _session_or_new(session)
    try:
        query = active_session.query(Job).order_by(desc(Job.discovered_at)).limit(limit)
        if status:
            query = query.filter(Job.status == status)
        if source:
            query = query.filter(Job.source == source)
        if q:
            like = f"%{q}%"
            query = query.filter((Job.title.ilike(like)) | (Job.company.ilike(like)) | (Job.description.ilike(like)))
        jobs = []
        for job in query.all():
            score = active_session.query(JobScore).filter(JobScore.job_id == job.id).order_by(desc(JobScore.created_at)).first()
            if min_score is not None and (not score or score.overall_score < min_score):
                continue
            jobs.append(serialize_job(job, score))
        return {"ok": True, "jobs": jobs, "count": len(jobs)}
    finally:
        if should_close:
            active_session.close()


def get_job(job_id: int, session: Session | None = None) -> dict[str, Any]:
    active_session, should_close = _session_or_new(session)
    try:
        job = active_session.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": f"Unknown job id: {job_id}"}
        score = active_session.query(JobScore).filter(JobScore.job_id == job.id).order_by(desc(JobScore.created_at)).first()
        events = []
        sessions = active_session.query(BrowserApplySession).filter(BrowserApplySession.job_id == job.id).order_by(desc(BrowserApplySession.created_at)).all()
        return {
            "ok": True,
            "job": serialize_job(job, score, include_detail=True),
            "browser_sessions": [serialize_browser_session(item) for item in sessions],
            "events": events,
        }
    finally:
        if should_close:
            active_session.close()


def serialize_browser_session(item: BrowserApplySession) -> dict:
    return {
        "id": item.id,
        "job_id": item.job_id,
        "status": item.status,
        "url": item.url,
        "screenshot_dir": item.screenshot_dir,
        "fields_detected": item.fields_detected,
        "fields_filled": item.fields_filled,
        "fields_blocked": item.fields_blocked,
        "requires_human": item.requires_human,
        "created_at": _serialize_dt(item.created_at),
        "metadata": item.metadata_json,
    }


def overview(session: Session | None = None) -> dict[str, Any]:
    active_session, should_close = _session_or_new(session)
    try:
        ensure_job_sources(active_session)
        total = active_session.query(Job).count()
        new_jobs = active_session.query(Job).filter(Job.status == "new").count()
        packets = active_session.query(Approval).filter(Approval.status == "requested").count()
        manual = active_session.query(Job).filter(Job.manual_required.is_(True)).count()
        submitted = 0
        top_scores = (
            active_session.query(Job, JobScore)
            .join(JobScore, JobScore.job_id == Job.id)
            .order_by(desc(JobScore.overall_score))
            .limit(5)
            .all()
        )
        sources = [
            {
                "id": src.id,
                "name": src.name,
                "type": src.type,
                "enabled": src.enabled,
                "health_status": src.health_status,
                "last_run_at": _serialize_dt(src.last_run_at),
                "last_error": src.last_error,
                "requires_api_key": src.requires_api_key,
                "restricted_mode": src.restricted_mode,
            }
            for src in active_session.query(JobSource).order_by(JobSource.name).all()
        ]
        runs = active_session.query(IngestionRun).order_by(desc(IngestionRun.started_at)).limit(10).all()
        return {
            "ok": True,
            "metrics": {
                "total_jobs": total,
                "new_jobs_today": new_jobs,
                "top_matches": len(top_scores),
                "ready_to_apply": active_session.query(JobScore).filter(JobScore.recommendation == "apply").count(),
                "needs_approval": packets,
                "blocked_manual": manual,
                "applications_submitted": submitted,
            },
            "top_jobs": [serialize_job(job, score) for job, score in top_scores],
            "sources": sources,
            "recent_runs": [serialize_run(run) for run in runs],
        }
    finally:
        if should_close:
            active_session.close()


def serialize_run(run: IngestionRun) -> dict:
    return {
        "id": run.id,
        "source": run.source,
        "started_at": _serialize_dt(run.started_at),
        "finished_at": _serialize_dt(run.finished_at),
        "status": run.status,
        "jobs_found": run.jobs_found,
        "jobs_new": run.jobs_new,
        "jobs_updated": run.jobs_updated,
        "jobs_deduped": run.jobs_deduped,
        "error": run.error,
        "metadata": run.metadata_json,
    }


def list_runs(session: Session | None = None) -> dict[str, Any]:
    active_session, should_close = _session_or_new(session)
    try:
        runs = active_session.query(IngestionRun).order_by(desc(IngestionRun.started_at)).limit(100).all()
        return {"ok": True, "runs": [serialize_run(run) for run in runs]}
    finally:
        if should_close:
            active_session.close()


def list_applications(session: Session | None = None) -> dict[str, Any]:
    active_session, should_close = _session_or_new(session)
    try:
        packets = active_session.query(Approval).order_by(desc(Approval.requested_at)).limit(100).all()
        return {"ok": True, "approvals": [serialize_approval(item) for item in packets]}
    finally:
        if should_close:
            active_session.close()


def list_sources(session: Session | None = None) -> dict[str, Any]:
    active_session, should_close = _session_or_new(session)
    try:
        ensure_job_sources(active_session)
        active_session.commit()
        return overview(active_session)["sources"]
    finally:
        if should_close:
            active_session.close()


def update_source(source_name: str, enabled: bool | None = None, metadata: dict | None = None) -> dict[str, Any]:
    with get_session() as session:
        ensure_job_sources(session)
        source = session.execute(select(JobSource).where(JobSource.name == source_name)).scalar_one_or_none()
        if source is None:
            return {"ok": False, "error": f"Unknown source: {source_name}"}
        if enabled is not None:
            source.enabled = enabled
        if metadata:
            source.metadata_json = {**(source.metadata_json or {}), **metadata}
        session.commit()
        return {"ok": True, "source": source_name, "enabled": source.enabled}


def set_job_status(job_id: int, status: str) -> dict[str, Any]:
    with get_session() as session:
        job = session.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": f"Unknown job id: {job_id}"}
        job.status = status
        session.commit()
        return {"ok": True, "job_id": job_id, "status": status}


def approve_job(job_id: int, notes: str = "") -> dict[str, Any]:
    with get_session() as session:
        job = session.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": f"Unknown job id: {job_id}"}
        packet = job.packets[-1] if job.packets else None
        if packet is None:
            profile = get_or_create_default_profile(session)
            score = session.query(JobScore).filter(JobScore.job_id == job.id, JobScore.profile_id == profile.id).one_or_none()
            packet = upsert_packet(session, job, profile, score)
        approval = approve_packet(session, packet.id, notes)
        job.status = "approved"
        session.commit()
        return {"ok": True, "approval": serialize_approval(approval)}


def reject_job(job_id: int, notes: str = "") -> dict[str, Any]:
    with get_session() as session:
        job = session.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": f"Unknown job id: {job_id}"}
        packet = job.packets[-1] if job.packets else None
        if packet:
            approval = reject_packet(session, packet.id, notes)
        else:
            approval = None
        job.status = "skipped"
        session.commit()
        return {"ok": True, "approval": serialize_approval(approval) if approval else None}


def start_apply_session(job_id: int, demo: bool = False) -> dict[str, Any]:
    with get_session() as session:
        job = session.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": f"Unknown job id: {job_id}"}
        profile = get_or_create_default_profile(session)
        browser_session = create_apply_session(session, job, profile, demo=demo)
        job.status = "manual_required" if browser_session.requires_human else "in_progress"
        session.commit()
        return {"ok": True, "browser_session": serialize_browser_session(browser_session)}


def submit_approved(job_id: int) -> dict[str, Any]:
    return {
        "ok": False,
        "job_id": job_id,
        "error": "Auto-submit is disabled. Dexter stops before final submit unless a future source-specific policy enables it.",
    }


def latest_report() -> dict[str, Any]:
    from backend.jobs.config import reports_dir

    path = reports_dir() / "latest_jobs_report.json"
    md_path = reports_dir() / "latest_jobs_report.md"
    if not path.exists():
        with get_session() as session:
            return generate_daily_report(session)
    import json

    return {
        "ok": True,
        "json_path": str(path),
        "markdown_path": str(md_path),
        "report": json.loads(path.read_text(encoding="utf-8")),
        "markdown": md_path.read_text(encoding="utf-8") if md_path.exists() else "",
    }
