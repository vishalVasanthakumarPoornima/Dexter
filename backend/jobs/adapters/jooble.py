from __future__ import annotations

import os

import requests

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import REQUEST_TIMEOUT, USER_AGENT, clean_html, first, infer_employment_type, infer_remote_type, load_fixture_json, parse_datetime
from backend.jobs.schemas import JobQuery


class JoobleAdapter:
    name = "jooble"
    source_type = "job_board_api"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def _api_key(self) -> str:
        return os.getenv(self.config.get("api_key_env") or "JOOBLE_API_KEY", "")

    def validate_config(self) -> SourceHealth:
        ok = bool(self._api_key())
        return SourceHealth(
            ok=ok,
            status="ok" if ok else "auth_required",
            message="Jooble API key configured." if ok else "Set JOOBLE_API_KEY after Jooble approves the key.",
            requires_api_key=True,
        )

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            payload = load_fixture_json("jooble_jobs.json")
        else:
            api_key = self._api_key()
            if not api_key:
                return []
            response = requests.post(
                f"https://jooble.org/api/{api_key}",
                json={"keywords": query.keywords or "software engineer intern", "location": query.location or ""},
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            payload = response.json()
        return [RawJob(source=self.name, payload=item, source_url="https://jooble.org/api") for item in payload.get("jobs", [])[: query.max_results]]

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        title = first(item.get("title"))
        description = clean_html(first(item.get("snippet") or item.get("description")))
        location = first(item.get("location"))
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
            source_job_id=first(item.get("id") or item.get("link")),
            source_url=first(item.get("source") or item.get("link") or raw.source_url),
            apply_url=first(item.get("link")),
            date_posted=parse_datetime(item.get("updated") or item.get("date")),
            raw=item,
            manual_required=True,
        )

    def supports_apply(self) -> bool:
        return False
