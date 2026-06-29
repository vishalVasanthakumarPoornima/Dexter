from __future__ import annotations

import base64
import os
from urllib.parse import urlencode

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import clean_html, fetch_json, first, infer_employment_type, infer_remote_type, load_fixture_json, parse_datetime
from backend.jobs.schemas import JobQuery


class CareerjetAdapter:
    name = "careerjet"
    source_type = "job_board_api"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def _api_key(self) -> str:
        return os.getenv(self.config.get("api_key_env") or "CAREERJET_API_KEY", "")

    def validate_config(self) -> SourceHealth:
        ok = bool(self._api_key())
        return SourceHealth(
            ok=ok,
            status="ok" if ok else "auth_required",
            message="Careerjet API key configured." if ok else "Careerjet requires a publisher API key.",
            requires_api_key=True,
        )

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            payload = load_fixture_json("careerjet_jobs.json")
            source_url = "fixture://careerjet"
        else:
            api_key = self._api_key()
            if not api_key:
                return []
            params = {
                "locale_code": self.config.get("locale_code") or "en_US",
                "keywords": query.keywords or "software engineer intern",
                "location": query.location or "",
                "pagesize": min(query.max_results or 20, 50),
                "page": 1,
            }
            source_url = "https://search.api.careerjet.net/v4/query?" + urlencode(params)
            token = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
            payload = fetch_json(source_url, headers={"Authorization": f"Basic {token}"})
        return [RawJob(source=self.name, payload=item, source_url=source_url) for item in payload.get("jobs", [])[: query.max_results]]

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        title = first(item.get("title"))
        description = clean_html(first(item.get("description")))
        location = first(item.get("locations") or item.get("location"))
        return JobCreate(
            title=title,
            company=first(item.get("company") or "Unknown Company"),
            location=location,
            remote_type=infer_remote_type(description, location),
            employment_type=infer_employment_type(title, description),
            internship_flag="intern" in f"{title} {description}".lower(),
            salary_min=item.get("salary_min"),
            salary_max=item.get("salary_max"),
            description=description,
            source=self.name,
            source_job_id=first(item.get("url") or item.get("id")),
            source_url=first(item.get("url") or raw.source_url),
            apply_url=first(item.get("url")),
            date_posted=parse_datetime(item.get("date")),
            raw=item,
            manual_required=True,
        )

    def supports_apply(self) -> bool:
        return False
