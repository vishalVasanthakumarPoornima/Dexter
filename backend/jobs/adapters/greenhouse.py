from __future__ import annotations

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import clean_html, fetch_json, first, infer_employment_type, infer_remote_type, load_fixture_json, parse_datetime
from backend.jobs.schemas import JobQuery


class GreenhouseAdapter:
    name = "greenhouse"
    source_type = "ats"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def validate_config(self) -> SourceHealth:
        companies = self.config.get("companies") or []
        return SourceHealth(ok=True, status="ok", message=f"{len(companies)} board token(s) configured.")

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            payload = load_fixture_json("greenhouse_jobs.json")
            return [RawJob(source=self.name, payload=item, source_url="fixture://greenhouse") for item in payload.get("jobs", [])]

        jobs: list[RawJob] = []
        for company in self.config.get("companies") or []:
            url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"
            payload = fetch_json(url)
            for item in payload.get("jobs", [])[: query.max_results]:
                jobs.append(RawJob(source=self.name, payload={**item, "board_token": company}, source_url=url))
        return jobs

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        offices = item.get("offices") or []
        departments = item.get("departments") or []
        location = first([office.get("name", "") for office in offices if isinstance(office, dict)] or [item.get("location", {}).get("name", "") if isinstance(item.get("location"), dict) else ""])
        description = clean_html(str(item.get("content") or ""))
        title = first(item.get("title"))
        return JobCreate(
            title=title,
            company=first(item.get("company_name") or item.get("board_token") or "Unknown Company"),
            location=location,
            remote_type=infer_remote_type(description, location),
            employment_type=infer_employment_type(title, description),
            internship_flag="intern" in title.lower() or "intern" in description.lower(),
            description=description,
            requirements=[],
            source=self.name,
            source_job_id=first(item.get("id")),
            source_url=raw.source_url,
            apply_url=first(item.get("absolute_url")),
            date_posted=parse_datetime(item.get("updated_at")),
            raw=item,
            metadata={"departments": departments, "offices": offices},
        )

    def supports_apply(self) -> bool:
        return False
