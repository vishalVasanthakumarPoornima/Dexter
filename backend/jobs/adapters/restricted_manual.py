from __future__ import annotations

from urllib.parse import urlparse

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import first, infer_employment_type
from backend.jobs.schemas import JobQuery


class RestrictedManualAdapter:
    name = "restricted_manual"
    source_type = "restricted_manual"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def validate_config(self) -> SourceHealth:
        return SourceHealth(
            ok=True,
            status="manual_only",
            message="Restricted platforms are stored as links only.",
            restricted_mode=True,
        )

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        url = query.keywords.strip()
        domains = self.config.get("domains") or ["linkedin.com", "indeed.com", "glassdoor.com"]
        if url.startswith(("http://", "https://")) and any(domain in urlparse(url).netloc for domain in domains):
            return [RawJob(source=self.name, payload={"url": url, "domain": urlparse(url).netloc}, source_url=url)]
        return []

    def normalize(self, raw: RawJob) -> JobCreate:
        url = raw.payload.get("url", "")
        domain = raw.payload.get("domain", "restricted")
        title = f"Manual application link from {domain}"
        return JobCreate(
            title=title,
            company=domain.replace("www.", ""),
            source=self.name,
            source_job_id=url,
            source_url=url,
            apply_url=url,
            employment_type=infer_employment_type(title),
            description="Restricted/manual source. Dexter will not scrape, bulk apply, or submit unattended.",
            raw=raw.payload,
            restricted=True,
            manual_required=True,
            metadata={"policy": "manual_only"},
        )

    def supports_apply(self) -> bool:
        return False
