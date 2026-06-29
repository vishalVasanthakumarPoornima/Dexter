from __future__ import annotations

import re
from urllib.parse import urljoin

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import fetch_text, infer_employment_type, infer_remote_type, load_fixture_text
from backend.jobs.schemas import JobQuery


ATS_PATTERNS = [
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.lever.co",
    "ashbyhq.com",
    "workdayjobs.com",
    "myworkdayjobs.com",
    "smartrecruiters.com",
    "icims.com",
    "workable.com",
    "bamboohr.com",
]


def discover_career_links(html: str, base_url: str) -> list[str]:
    links = []
    for match in re.finditer(r'href=["\']([^"\']+)["\']', html, flags=re.I):
        href = urljoin(base_url, match.group(1))
        lower = href.lower()
        if any(pattern in lower for pattern in ATS_PATTERNS) or "career" in lower or "job" in lower:
            links.append(href)
    return list(dict.fromkeys(links))[:50]


class CompanyCareersAdapter:
    name = "company_careers"
    source_type = "discovery"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def validate_config(self) -> SourceHealth:
        return SourceHealth(ok=True, status="ok", message="Career discovery enabled.")

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            html = load_fixture_text("company_careers.html")
            links = discover_career_links(html, "https://example.com/careers")
            return [RawJob(source=self.name, payload={"url": link, "company": "Example"}, source_url="fixture://company_careers") for link in links]

        jobs = []
        for company in self.config.get("companies") or []:
            url = company if str(company).startswith("http") else f"https://{company}"
            try:
                links = discover_career_links(fetch_text(url), url)
            except Exception:
                links = []
            jobs.extend(RawJob(source=self.name, payload={"url": link, "company": company}, source_url=url) for link in links)
        return jobs

    def normalize(self, raw: RawJob) -> JobCreate:
        url = raw.payload.get("url", "")
        title = "Career page discovered"
        return JobCreate(
            title=title,
            company=str(raw.payload.get("company") or "Company career page"),
            source=self.name,
            source_job_id=url,
            source_url=raw.source_url,
            apply_url=url,
            employment_type=infer_employment_type(title),
            remote_type=infer_remote_type(url),
            description=f"Potential career/application URL discovered: {url}",
            raw=raw.payload,
            manual_required=True,
            metadata={"discovery_only": True},
        )

    def supports_apply(self) -> bool:
        return False
