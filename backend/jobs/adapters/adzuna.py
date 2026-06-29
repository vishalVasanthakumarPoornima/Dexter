from __future__ import annotations

import os

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import clean_html, fetch_json, first, infer_employment_type, infer_remote_type, load_fixture_json, parse_datetime
from backend.jobs.schemas import JobQuery


class AdzunaAdapter:
    name = "adzuna"
    source_type = "job_board_api"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def _credentials(self) -> tuple[str, str]:
        return (
            os.getenv(self.config.get("app_id_env") or "ADZUNA_APP_ID", ""),
            os.getenv(self.config.get("app_key_env") or "ADZUNA_APP_KEY", ""),
        )

    def validate_config(self) -> SourceHealth:
        app_id, app_key = self._credentials()
        ok = bool(app_id and app_key)
        return SourceHealth(
            ok=ok,
            status="ok" if ok else "auth_required",
            message="Adzuna credentials configured." if ok else "Set ADZUNA_APP_ID and ADZUNA_APP_KEY.",
            requires_api_key=True,
        )

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            payload = load_fixture_json("adzuna_jobs.json")
        else:
            app_id, app_key = self._credentials()
            if not app_id or not app_key:
                return []
            what = (query.keywords or "software engineer").replace(" ", "%20")
            where = (query.location or "remote").replace(" ", "%20")
            url = f"https://api.adzuna.com/v1/api/jobs/us/search/1?app_id={app_id}&app_key={app_key}&what={what}&where={where}"
            payload = fetch_json(url)
        return [RawJob(source=self.name, payload=item, source_url="https://api.adzuna.com/v1/api/jobs") for item in payload.get("results", [])[: query.max_results]]

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        title = first(item.get("title"))
        description = clean_html(first(item.get("description")))
        location = first(item.get("location", {}).get("display_name") if isinstance(item.get("location"), dict) else "")
        return JobCreate(
            title=title,
            company=first(item.get("company", {}).get("display_name") if isinstance(item.get("company"), dict) else "Unknown Company"),
            location=location,
            remote_type=infer_remote_type(description, location),
            employment_type=infer_employment_type(title, description),
            internship_flag="intern" in title.lower() or "intern" in description.lower(),
            salary_min=item.get("salary_min"),
            salary_max=item.get("salary_max"),
            description=description,
            source=self.name,
            source_job_id=first(item.get("id")),
            source_url=first(item.get("redirect_url") or raw.source_url),
            apply_url=first(item.get("redirect_url")),
            date_posted=parse_datetime(item.get("created")),
            raw=item,
            manual_required=True,
        )

    def supports_apply(self) -> bool:
        return False
