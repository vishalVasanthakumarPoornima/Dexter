from __future__ import annotations

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import clean_html, clean_text, fetch_json, first, infer_employment_type, infer_remote_type, load_fixture_json, parse_datetime
from backend.jobs.schemas import JobQuery


class LeverAdapter:
    name = "lever"
    source_type = "ats"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def validate_config(self) -> SourceHealth:
        companies = self.config.get("companies") or []
        return SourceHealth(ok=True, status="ok", message=f"{len(companies)} site slug(s) configured.")

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            payload = load_fixture_json("lever_postings.json")
            return [RawJob(source=self.name, payload=item, source_url="fixture://lever") for item in payload]

        jobs: list[RawJob] = []
        for company in self.config.get("companies") or []:
            url = f"https://api.lever.co/v0/postings/{company}?mode=json"
            payload = fetch_json(url)
            for item in payload[: query.max_results]:
                jobs.append(RawJob(source=self.name, payload={**item, "site_slug": company}, source_url=url))
        return jobs

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        lists = item.get("lists") or []
        description_parts = [item.get("descriptionPlain") or clean_html(str(item.get("description") or ""))]
        for block in lists:
            if isinstance(block, dict):
                description_parts.append(clean_html(str(block.get("content") or "")))
        description = clean_text(" ".join(description_parts))
        title = first(item.get("text"))
        salary = item.get("salaryRange") or {}
        return JobCreate(
            title=title,
            company=first(item.get("categories", {}).get("team") or item.get("site_slug") or "Unknown Company"),
            location=first(item.get("categories", {}).get("location")),
            remote_type=infer_remote_type(description, first(item.get("categories", {}).get("location"))),
            employment_type=first(item.get("categories", {}).get("commitment")) or infer_employment_type(title, description),
            internship_flag="intern" in title.lower() or "intern" in description.lower(),
            salary_min=salary.get("min") if isinstance(salary, dict) else None,
            salary_max=salary.get("max") if isinstance(salary, dict) else None,
            description=description,
            source=self.name,
            source_job_id=first(item.get("id")),
            source_url=first(item.get("hostedUrl") or raw.source_url),
            apply_url=first(item.get("applyUrl") or item.get("hostedUrl")),
            date_posted=parse_datetime(item.get("createdAt")),
            raw=item,
        )

    def supports_apply(self) -> bool:
        return False
