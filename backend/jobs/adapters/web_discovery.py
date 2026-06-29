from __future__ import annotations

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import infer_employment_type
from backend.jobs.schemas import JobQuery


DEFAULT_QUERIES = [
    "software engineer intern 2027 greenhouse",
    "AI intern jobs 2027 greenhouse",
    "security engineer intern 2027 lever",
    "site:boards.greenhouse.io software engineer intern",
    "site:jobs.lever.co AI security intern",
    "site:github.com 2027 software engineering internships",
]


class WebDiscoveryAdapter:
    name = "web_discovery"
    source_type = "search_discovery"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def validate_config(self) -> SourceHealth:
        return SourceHealth(ok=True, status="manual_review", message="Discovery queries produce review links.")

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        queries = self.config.get("queries") or DEFAULT_QUERIES
        if query.keywords:
            queries = [query.keywords, *queries]
        rows = []
        for item in queries[: min(query.max_results, 25)]:
            rows.append(
                RawJob(
                    source=self.name,
                    payload={
                        "query": item,
                        "url": "https://www.google.com/search?q=" + item.replace(" ", "+"),
                    },
                    source_url="configured_search_templates",
                )
            )
        return rows

    def normalize(self, raw: RawJob) -> JobCreate:
        query = raw.payload.get("query", "")
        url = raw.payload.get("url", "")
        return JobCreate(
            title=f"Discovery search: {query}",
            company="Web discovery",
            source=self.name,
            source_job_id=url,
            source_url=raw.source_url,
            apply_url=url,
            employment_type=infer_employment_type(query),
            description="Search-discovery candidate. Route resulting URLs into ATS/manual adapters after review.",
            raw=raw.payload,
            manual_required=True,
            metadata={"low_confidence": True},
        )

    def supports_apply(self) -> bool:
        return False
