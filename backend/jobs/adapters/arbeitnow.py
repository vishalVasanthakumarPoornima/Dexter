from __future__ import annotations

from datetime import datetime, timezone

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import clean_html, fetch_json, first, infer_employment_type, infer_remote_type, load_fixture_json
from backend.jobs.schemas import JobQuery


class ArbeitnowAdapter:
    name = "arbeitnow"
    source_type = "job_board_api"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def validate_config(self) -> SourceHealth:
        return SourceHealth(ok=True, status="ok", message="Free public API; no key required.")

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            payload = load_fixture_json("arbeitnow_jobs.json")
            source_url = "fixture://arbeitnow"
        else:
            limit = max(1, min(query.max_results or 100, 100))
            source_url = f"https://www.arbeitnow.com/api/job-board-api?limit={limit}"
            payload = fetch_json(source_url)
        return [RawJob(source=self.name, payload=item, source_url=source_url) for item in payload.get("data", [])[: query.max_results]]

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        title = first(item.get("title"))
        description = clean_html(first(item.get("description")))
        location = first(item.get("location"))
        created_at = item.get("created_at")
        posted = datetime.fromtimestamp(created_at, timezone.utc) if isinstance(created_at, (int, float)) else None
        remote_type = "remote" if item.get("remote") else infer_remote_type(description, location)
        tags = [first(tag) for tag in item.get("tags") or []]
        job_types = [first(job_type) for job_type in item.get("job_types") or []]
        return JobCreate(
            title=title,
            company=first(item.get("company_name") or "Unknown Company"),
            location=location,
            remote_type=remote_type,
            employment_type=infer_employment_type(title, " ".join([description, *job_types])),
            internship_flag="intern" in f"{title} {description} {' '.join(job_types)}".lower(),
            description=description,
            requirements=tags,
            source=self.name,
            source_job_id=first(item.get("slug")),
            source_url=first(item.get("url") or raw.source_url),
            apply_url=first(item.get("url")),
            date_posted=posted,
            raw=item,
            manual_required=True,
            metadata={"tags": tags, "job_types": job_types},
        )

    def supports_apply(self) -> bool:
        return False
