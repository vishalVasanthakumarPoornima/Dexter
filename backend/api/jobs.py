from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Query

from backend.jobs.db import init_db
from backend.jobs.reports import generate_daily_report
from backend.jobs.schemas import ApprovalRequest, IngestRequest, JobQuery, ManualLinkRequest, PacketRequest, SourceUpdateRequest
from backend.jobs.service import (
    approve_job,
    generate_packet_for_job,
    get_job,
    ingest_jobs,
    latest_report,
    list_applications,
    list_jobs,
    list_runs,
    list_sources,
    overview,
    reject_job,
    run_daily,
    score_jobs,
    set_job_status,
    start_apply_session,
    submit_approved,
    update_source,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/overview")
def jobs_overview():
    init_db()
    return overview()


@router.get("/sources")
def jobs_sources():
    init_db()
    return {"ok": True, "sources": list_sources()}


@router.patch("/sources/{source_id}")
def jobs_source_update(source_id: str, req: SourceUpdateRequest):
    return update_source(source_id, enabled=req.enabled, metadata=req.metadata)


@router.get("/runs")
def jobs_runs():
    return list_runs()


@router.get("/applications")
def jobs_applications():
    return list_applications()


@router.get("/reports/latest")
def jobs_latest_report():
    return latest_report()


@router.post("/run-daily")
def jobs_run_daily(demo: bool = False):
    return run_daily(demo=demo)


@router.post("/manual-link")
def jobs_manual_link(req: ManualLinkRequest):
    host = urlparse(req.url).netloc.lower()
    restricted = any(domain in host for domain in ("linkedin.com", "indeed.com", "glassdoor.com"))
    source = "restricted_manual" if restricted else "manual_link"
    result = ingest_jobs(source=source, query=JobQuery(keywords=req.url), demo=False)
    result["manual_link"] = {"url": req.url, "restricted": restricted, "notes": req.notes}
    return result


@router.get("")
def jobs_list(
    status: str | None = None,
    source: str | None = None,
    q: str | None = None,
    min_score: float | None = Query(default=None),
    limit: int = 100,
):
    return list_jobs(status=status, source=source, q=q, min_score=min_score, limit=limit)


@router.post("/ingest")
def jobs_ingest(req: IngestRequest):
    return ingest_jobs(source=req.source, query=req.query, demo=req.demo, dry_run=req.dry_run)


@router.post("/score")
def jobs_score(profile_id: int | None = None):
    return score_jobs(profile_id=profile_id)


@router.get("/{job_id}")
def jobs_detail(job_id: int):
    return get_job(job_id)


@router.post("/{job_id}/packet")
def jobs_packet(job_id: int, req: PacketRequest | None = None):
    request = req or PacketRequest()
    return generate_packet_for_job(job_id=job_id, profile_id=request.profile_id)


@router.post("/{job_id}/approve")
def jobs_approve(job_id: int, req: ApprovalRequest | None = None):
    return approve_job(job_id, notes=(req.notes if req else ""))


@router.post("/{job_id}/skip")
def jobs_skip(job_id: int, req: ApprovalRequest | None = None):
    return reject_job(job_id, notes=(req.notes if req else ""))


@router.post("/{job_id}/archive")
def jobs_archive(job_id: int):
    return set_job_status(job_id, "archived")


@router.post("/{job_id}/apply-session")
def jobs_apply_session(job_id: int, demo: bool = False):
    return start_apply_session(job_id, demo=demo)


@router.post("/{job_id}/submit-approved")
def jobs_submit_approved(job_id: int):
    return submit_approved(job_id)
