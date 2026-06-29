from __future__ import annotations

import os
from urllib.parse import quote_plus

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import clean_html, fetch_json, first, infer_employment_type, load_fixture_json
from backend.jobs.schemas import JobQuery


DEFAULT_BRAVE_QUERIES = [
    'site:jobs.ashbyhq.com "software engineer intern"',
    'site:jobs.smartrecruiters.com "software engineer intern"',
    'site:*.recruitee.com "software engineer intern"',
    'site:www.themuse.com/jobs "software engineer intern"',
]


class BraveSearchAdapter:
    name = "brave_search"
    source_type = "search_api"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def _api_key(self) -> str:
        return os.getenv(self.config.get("api_key_env") or "BRAVE_SEARCH_API_KEY", "")

    def validate_config(self) -> SourceHealth:
        ok = bool(self._api_key())
        return SourceHealth(
            ok=ok,
            status="ok" if ok else "auth_required",
            message="Brave Search API key configured." if ok else "Set BRAVE_SEARCH_API_KEY to enable search API discovery.",
            requires_api_key=True,
        )

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            payload = load_fixture_json("brave_search_results.json")
            return [RawJob(source=self.name, payload=item, source_url="fixture://brave_search") for item in payload.get("web", {}).get("results", [])[: query.max_results]]

        api_key = self._api_key()
        if not api_key:
            return []
        queries = self.config.get("queries") or DEFAULT_BRAVE_QUERIES
        if query.keywords:
            queries = [query.keywords, *queries]
        jobs: list[RawJob] = []
        for search_query in queries[:5]:
            url = f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(search_query)}&count={min(query.max_results, 20)}"
            payload = fetch_json(url, headers={"Accept": "application/json", "X-Subscription-Token": api_key})
            for item in payload.get("web", {}).get("results", []):
                jobs.append(RawJob(source=self.name, payload={**item, "query": search_query}, source_url=url))
        return jobs[: query.max_results]

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        title = first(item.get("title"))
        description = clean_html(first(item.get("description") or item.get("extra_snippets", [""])))
        url = first(item.get("url"))
        return JobCreate(
            title=title or f"Search result: {item.get('query', '')}",
            company="Brave Search discovery",
            employment_type=infer_employment_type(title, description),
            description=description,
            source=self.name,
            source_job_id=url,
            source_url=raw.source_url,
            apply_url=url,
            raw=item,
            manual_required=True,
            metadata={"query": item.get("query"), "low_confidence": True},
        )

    def supports_apply(self) -> bool:
        return False
