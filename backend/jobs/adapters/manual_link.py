from __future__ import annotations

from urllib.parse import urlparse

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import clean_html, fetch_text, first, infer_employment_type, infer_remote_type
from backend.jobs.schemas import JobQuery


class ManualLinkAdapter:
    name = "manual_link"
    source_type = "manual"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def validate_config(self) -> SourceHealth:
        return SourceHealth(ok=True, status="ok", message="Manual link capture enabled.")

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        url = query.keywords.strip()
        if not url.startswith(("http://", "https://")):
            return []
        title = ""
        description = ""
        try:
            html = fetch_text(url)
            description = clean_html(html[:5000])
            if "<title" in html.lower():
                start = html.lower().find("<title")
                title_text = html[start : start + 500]
                title = clean_html(title_text)
        except Exception:
            description = "Manual-review job link. Dexter could not fetch metadata."
        return [RawJob(source=self.name, payload={"url": url, "title": title, "description": description}, source_url=url)]

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        parsed = urlparse(item.get("url", ""))
        title = first(item.get("title") or "Manual job link")
        description = first(item.get("description"))
        return JobCreate(
            title=title[:240],
            company=parsed.netloc.replace("www.", "") or "Manual Review",
            location="",
            remote_type=infer_remote_type(description),
            employment_type=infer_employment_type(title, description),
            internship_flag="intern" in title.lower() or "intern" in description.lower(),
            description=description,
            source=self.name,
            source_job_id=item.get("url", ""),
            source_url=item.get("url", ""),
            apply_url=item.get("url", ""),
            raw=item,
            manual_required=True,
        )

    def supports_apply(self) -> bool:
        return False
