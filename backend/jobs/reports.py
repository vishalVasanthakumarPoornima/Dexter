from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import desc

from backend.jobs.config import reports_dir
from backend.jobs.models import ApplicationPacket, Job, JobScore


def generate_daily_report(session, limit: int = 20) -> dict:
    rows = (
        session.query(Job, JobScore)
        .join(JobScore, JobScore.job_id == Job.id)
        .order_by(desc(JobScore.overall_score), desc(Job.discovered_at))
        .limit(limit)
        .all()
    )
    created_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_rows = []
    for job, score in rows:
        packet = (
            session.query(ApplicationPacket)
            .filter(ApplicationPacket.job_id == job.id, ApplicationPacket.profile_id == score.profile_id)
            .one_or_none()
        )
        report_rows.append(
            {
                "job_id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "score": score.overall_score,
                "recommendation": score.recommendation,
                "match_reasons": score.match_reasons,
                "gaps": score.gaps,
                "apply_url": job.apply_url,
                "packet_status": "generated" if packet else "not_generated",
                "approval_needed": bool(packet),
                "manual_required": job.manual_required,
            }
        )

    markdown = ["# Dexter Jobs Daily Report", "", f"Generated: {datetime.now(timezone.utc).isoformat()}", ""]
    if not report_rows:
        markdown.append("No scored jobs yet. Run demo or ingestion first.")
    for item in report_rows:
        markdown.extend(
            [
                f"## {item['score']:.1f} - {item['title']} at {item['company']}",
                f"- Location: {item['location'] or 'Unknown'}",
                f"- Recommendation: {item['recommendation']}",
                f"- Apply: {item['apply_url'] or 'No apply URL'}",
                f"- Why: {', '.join(item['match_reasons']) or 'No reasons recorded'}",
                f"- Gaps: {', '.join(item['gaps']) or 'None recorded'}",
                f"- Packet: {item['packet_status']}",
                "",
            ]
        )

    out_dir = reports_dir()
    md_path = out_dir / f"jobs_report_{created_at}.md"
    json_path = out_dir / f"jobs_report_{created_at}.json"
    latest_md = out_dir / "latest_jobs_report.md"
    latest_json = out_dir / "latest_jobs_report.json"
    payload = {"created_at": created_at, "jobs": report_rows}
    md_text = "\n".join(markdown)
    md_path.write_text(md_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    latest_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "created_at": created_at,
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "latest_markdown_path": str(latest_md),
        "latest_json_path": str(latest_json),
        "jobs": report_rows,
    }
