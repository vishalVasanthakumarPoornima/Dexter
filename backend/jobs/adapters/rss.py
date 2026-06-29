from __future__ import annotations

import xml.etree.ElementTree as ET

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import clean_html, fetch_text, first, infer_employment_type, infer_remote_type, load_fixture_text, parse_datetime
from backend.jobs.schemas import JobQuery


def parse_rss_items(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items: list[dict] = []
    for item in root.findall(".//item"):
        def text(name: str) -> str:
            node = item.find(name)
            return node.text.strip() if node is not None and node.text else ""

        items.append(
            {
                "title": text("title"),
                "link": text("link"),
                "description": text("description"),
                "pubDate": text("pubDate"),
            }
        )
    for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        title = entry.find("{http://www.w3.org/2005/Atom}title")
        link = entry.find("{http://www.w3.org/2005/Atom}link")
        summary = entry.find("{http://www.w3.org/2005/Atom}summary")
        updated = entry.find("{http://www.w3.org/2005/Atom}updated")
        items.append(
            {
                "title": title.text if title is not None and title.text else "",
                "link": link.get("href", "") if link is not None else "",
                "description": summary.text if summary is not None and summary.text else "",
                "pubDate": updated.text if updated is not None and updated.text else "",
            }
        )
    return items


class RSSAdapter:
    name = "rss"
    source_type = "feed"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def validate_config(self) -> SourceHealth:
        feeds = self.config.get("feeds") or []
        return SourceHealth(ok=True, status="ok", message=f"{len(feeds)} feed(s) configured.")

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            rows = parse_rss_items(load_fixture_text("rss_feed.xml"))
            return [RawJob(source=self.name, payload=row, source_url="fixture://rss") for row in rows]

        jobs: list[RawJob] = []
        for feed in self.config.get("feeds") or []:
            rows = parse_rss_items(fetch_text(feed))
            jobs.extend(RawJob(source=self.name, payload=row, source_url=feed) for row in rows[: query.max_results])
        return jobs

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        title = first(item.get("title"))
        description = clean_html(item.get("description", ""))
        company = "Unknown Company"
        if " at " in title:
            title, company = title.rsplit(" at ", 1)
        return JobCreate(
            title=title,
            company=company,
            location="",
            remote_type=infer_remote_type(description),
            employment_type=infer_employment_type(title, description),
            internship_flag="intern" in title.lower() or "intern" in description.lower(),
            description=description,
            source=self.name,
            source_job_id=item.get("link", ""),
            source_url=raw.source_url,
            apply_url=item.get("link", ""),
            date_posted=parse_datetime(item.get("pubDate")),
            raw=item,
            manual_required=True,
        )

    def supports_apply(self) -> bool:
        return False
