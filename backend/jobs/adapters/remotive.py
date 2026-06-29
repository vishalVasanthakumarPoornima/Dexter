from __future__ import annotations

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import clean_html, fetch_json, first, infer_employment_type, load_fixture_json, parse_datetime
from backend.jobs.schemas import JobQuery


class RemotiveAdapter:
    name = "remotive"
    source_type = "remote_board"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def validate_config(self) -> SourceHealth:
        return SourceHealth(ok=True, status="ok", message="No API key required.")

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            payload = load_fixture_json("remotive_jobs.json")
        else:
            endpoint = "https://remotive.com/api/remote-jobs"
            if query.keywords:
                endpoint += f"?search={query.keywords.replace(' ', '%20')}"
            payload = fetch_json(endpoint)
        return [RawJob(source=self.name, payload=item, source_url="https://remotive.com/api/remote-jobs") for item in payload.get("jobs", [])[: query.max_results]]

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        title = first(item.get("title"))
        description = clean_html(str(item.get("description") or ""))
        return JobCreate(
            title=title,
            company=first(item.get("company_name")),
            location=first(item.get("candidate_required_location") or "Remote"),
            remote_type="remote",
            employment_type=infer_employment_type(title, description),
            internship_flag="intern" in title.lower() or "intern" in description.lower(),
            description=description,
            requirements=item.get("tags") or [],
            source=self.name,
            source_job_id=first(item.get("id")),
            source_url=first(item.get("url")),
            apply_url=first(item.get("url")),
            date_posted=parse_datetime(item.get("publication_date")),
            raw=item,
            metadata={"category": item.get("category"), "tags": item.get("tags") or []},
        )

    def supports_apply(self) -> bool:
        return False
