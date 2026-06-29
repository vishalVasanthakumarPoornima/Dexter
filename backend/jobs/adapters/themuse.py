from __future__ import annotations

import os
from urllib.parse import urlencode

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import clean_html, fetch_json, first, infer_employment_type, infer_remote_type, load_fixture_json, parse_datetime
from backend.jobs.schemas import JobQuery


class TheMuseAdapter:
    name = "themuse"
    source_type = "job_board_api"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def _api_key(self) -> str:
        return os.getenv(self.config.get("api_key_env") or "THEMUSE_API_KEY", "")

    def validate_config(self) -> SourceHealth:
        return SourceHealth(ok=True, status="ok", message="No key required; optional THEMUSE_API_KEY raises rate limit.")

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            payload = load_fixture_json("themuse_jobs.json")
            source_url = "fixture://themuse"
        else:
            params = {"page": 0}
            if query.location:
                params["location"] = query.location
            categories = self.config.get("categories") or []
            if categories:
                params["category"] = categories[0]
            api_key = self._api_key()
            if api_key:
                params["api_key"] = api_key
            source_url = "https://www.themuse.com/api/public/jobs?" + urlencode(params)
            payload = fetch_json(source_url)
        return [RawJob(source=self.name, payload=item, source_url=source_url) for item in payload.get("results", [])[: query.max_results]]

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        title = first(item.get("name"))
        description = clean_html(first(item.get("contents")))
        locations = "; ".join(first(loc.get("name")) for loc in item.get("locations", []) if isinstance(loc, dict))
        company = item.get("company") if isinstance(item.get("company"), dict) else {}
        levels = [first(level.get("name")) for level in item.get("levels", []) if isinstance(level, dict)]
        categories = [first(category.get("name")) for category in item.get("categories", []) if isinstance(category, dict)]
        refs = item.get("refs") if isinstance(item.get("refs"), dict) else {}
        return JobCreate(
            title=title,
            company=first(company.get("name") or "Unknown Company"),
            location=locations,
            remote_type=infer_remote_type(description, locations),
            employment_type=infer_employment_type(title, " ".join([description, *levels])),
            internship_flag="intern" in f"{title} {description}".lower(),
            seniority=", ".join(levels),
            description=description,
            requirements=categories,
            source=self.name,
            source_job_id=first(item.get("id")),
            source_url=first(refs.get("landing_page") or raw.source_url),
            apply_url=first(refs.get("landing_page")),
            date_posted=parse_datetime(item.get("publication_date")),
            raw=item,
            manual_required=True,
            metadata={"categories": categories, "levels": levels},
        )

    def supports_apply(self) -> bool:
        return False
