from __future__ import annotations

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import clean_html, fetch_json, first, infer_employment_type, infer_remote_type, load_fixture_json, parse_datetime
from backend.jobs.schemas import JobQuery


class RecruiteeAdapter:
    name = "recruitee"
    source_type = "ats"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def _companies(self) -> list[str]:
        return [str(company).strip() for company in self.config.get("companies", []) if str(company).strip()]

    def validate_config(self) -> SourceHealth:
        companies = self._companies()
        return SourceHealth(ok=True, status="ok", message=f"{len(companies)} Recruitee company subdomain(s) configured; no key required.")

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            payload = load_fixture_json("recruitee_offers.json")
            items = payload.get("offers", payload if isinstance(payload, list) else [])
            return [RawJob(source=self.name, payload={**item, "company_subdomain": "fixture"}, source_url="fixture://recruitee") for item in items[: query.max_results]]

        jobs: list[RawJob] = []
        for company in self._companies():
            url = f"https://{company}.recruitee.com/api/offers/"
            payload = fetch_json(url)
            items = payload.get("offers", payload if isinstance(payload, list) else [])
            for item in items[: query.max_results]:
                jobs.append(RawJob(source=self.name, payload={**item, "company_subdomain": company}, source_url=url))
        return jobs

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        title = first(item.get("title"))
        description = clean_html(first(item.get("description") or item.get("description_html")))
        requirements = clean_html(first(item.get("requirements") or item.get("requirements_html")))
        location = first(item.get("location") or item.get("city") or item.get("country"))
        careers_url = first(item.get("careers_url") or item.get("url") or item.get("apply_url"))
        return JobCreate(
            title=title,
            company=first(item.get("company_name") or item.get("company_subdomain") or "Unknown Company"),
            location=location,
            remote_type="remote" if item.get("remote") else infer_remote_type(description, location),
            employment_type=infer_employment_type(title, description),
            internship_flag="intern" in f"{title} {description}".lower(),
            description=" ".join(part for part in [description, requirements] if part),
            requirements=[requirements] if requirements else [],
            source=self.name,
            source_job_id=first(item.get("id") or item.get("slug") or careers_url),
            source_url=careers_url or raw.source_url,
            apply_url=careers_url,
            date_posted=parse_datetime(item.get("created_at") or item.get("published_at")),
            raw=item,
            manual_required=True,
            metadata={"department": item.get("department"), "company_subdomain": item.get("company_subdomain")},
        )

    def supports_apply(self) -> bool:
        return False
