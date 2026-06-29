from __future__ import annotations

import os

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import fetch_json, first, infer_employment_type, infer_remote_type, load_fixture_json, parse_datetime
from backend.jobs.schemas import JobQuery


class USAJobsAdapter:
    name = "usajobs"
    source_type = "official_api"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def _headers(self) -> dict[str, str]:
        key = os.getenv(self.config.get("api_key_env") or "USAJOBS_API_KEY", "")
        email = os.getenv(self.config.get("email_env") or "USAJOBS_EMAIL", "")
        return {"Authorization-Key": key, "User-Agent": email}

    def validate_config(self) -> SourceHealth:
        headers = self._headers()
        ok = bool(headers["Authorization-Key"] and headers["User-Agent"])
        return SourceHealth(
            ok=ok,
            status="ok" if ok else "auth_required",
            message="USAJOBS API key and email configured." if ok else "Set USAJOBS_API_KEY and USAJOBS_EMAIL.",
            requires_api_key=True,
        )

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            payload = load_fixture_json("usajobs_search.json")
        else:
            health = self.validate_config()
            if not health.ok:
                return []
            params = f"Keyword={query.keywords or 'software engineer'}"
            if query.location:
                params += f"&LocationName={query.location}"
            url = f"https://data.usajobs.gov/api/search?{params}"
            payload = fetch_json(url, headers=self._headers())
        items = payload.get("SearchResult", {}).get("SearchResultItems", [])
        return [RawJob(source=self.name, payload=item.get("MatchedObjectDescriptor", item), source_url="https://data.usajobs.gov/api/search") for item in items[: query.max_results]]

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        title = first(item.get("PositionTitle"))
        locations = item.get("PositionLocation") or []
        location = "; ".join(first(loc.get("LocationName")) for loc in locations if isinstance(loc, dict))
        description = first(item.get("QualificationSummary") or item.get("UserArea", {}).get("Details", {}).get("JobSummary"))
        salary = item.get("PositionRemuneration") or [{}]
        salary_item = salary[0] if salary and isinstance(salary[0], dict) else {}
        return JobCreate(
            title=title,
            company=first(item.get("OrganizationName") or item.get("DepartmentName") or "US Federal Government"),
            location=location,
            remote_type=infer_remote_type(description, location),
            employment_type=infer_employment_type(title, description),
            internship_flag="intern" in title.lower() or "student" in description.lower(),
            salary_min=float(salary_item.get("MinimumRange") or 0) or None,
            salary_max=float(salary_item.get("MaximumRange") or 0) or None,
            currency=first(salary_item.get("RateIntervalCode") or "USD"),
            description=description,
            requirements=[description] if description else [],
            source=self.name,
            source_job_id=first(item.get("PositionID")),
            source_url=first(item.get("PositionURI") or raw.source_url),
            apply_url=first(item.get("ApplyURI", [""])),
            date_posted=parse_datetime(item.get("PublicationStartDate")),
            raw=item,
            manual_required=True,
            metadata={"source_confidence": 0.95},
        )

    def supports_apply(self) -> bool:
        return False
