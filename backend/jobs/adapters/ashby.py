from __future__ import annotations

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import clean_html, fetch_json, first, infer_employment_type, infer_remote_type, load_fixture_json, parse_datetime
from backend.jobs.schemas import JobQuery


class AshbyAdapter:
    name = "ashby"
    source_type = "ats"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def _boards(self) -> list[str]:
        return [str(board).strip() for board in (self.config.get("boards") or self.config.get("companies") or []) if str(board).strip()]

    def validate_config(self) -> SourceHealth:
        boards = self._boards()
        return SourceHealth(ok=True, status="ok", message=f"{len(boards)} Ashby board(s) configured; no key required.")

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            payload = load_fixture_json("ashby_jobs.json")
            return [RawJob(source=self.name, payload={**item, "board": "fixture"}, source_url="fixture://ashby") for item in payload.get("jobs", [])[: query.max_results]]

        jobs: list[RawJob] = []
        for board in self._boards():
            url = f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"
            payload = fetch_json(url)
            for item in payload.get("jobs", [])[: query.max_results]:
                jobs.append(RawJob(source=self.name, payload={**item, "board": board}, source_url=url))
        return jobs

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        title = first(item.get("title"))
        description = clean_html(first(item.get("descriptionHtml") or item.get("descriptionPlain")))
        location = first(item.get("location"))
        compensation = item.get("compensation") or {}
        salary_text = first(compensation.get("scrapeableCompensationSalarySummary") or compensation.get("compensationTierSummary"))
        remote_type = "remote" if item.get("isRemote") else infer_remote_type(description, location)
        return JobCreate(
            title=title,
            company=first(item.get("companyName") or item.get("organization") or item.get("board") or "Unknown Company"),
            location=location,
            remote_type=first(item.get("workplaceType")).lower() or remote_type,
            employment_type=infer_employment_type(title, first(item.get("employmentType") or description)),
            internship_flag="intern" in f"{title} {description}".lower(),
            description=description,
            benefits=[salary_text] if salary_text else [],
            source=self.name,
            source_job_id=first(item.get("id") or item.get("jobId") or item.get("jobUrl")),
            source_url=first(item.get("jobUrl") or raw.source_url),
            apply_url=first(item.get("applyUrl") or item.get("jobUrl")),
            date_posted=parse_datetime(item.get("publishedAt") or item.get("updatedAt")),
            raw=item,
            manual_required=True,
            metadata={
                "department": item.get("department"),
                "team": item.get("team"),
                "compensation": compensation,
                "board": item.get("board"),
            },
        )

    def supports_apply(self) -> bool:
        return False
