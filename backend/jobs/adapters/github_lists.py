from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import clean_text, fetch_text, github_raw_url, infer_employment_type, infer_remote_type, load_fixture_text
from backend.jobs.schemas import JobQuery


LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
GITHUB_REPO_RE = re.compile(r"^https://github\.com/([^/]+)/([^/#?]+)/*$")


def parse_markdown_jobs(markdown: str, source_url: str = "") -> list[dict]:
    jobs: list[dict] = []
    for line in markdown.splitlines():
        if "|" not in line or re.match(r"^\s*\|?\s*-{2,}", line):
            continue
        cells = [clean_text(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        header_blob = " ".join(c.lower() for c in cells)
        if "company" in header_blob and ("role" in header_blob or "position" in header_blob):
            continue
        company, role, location = cells[0], cells[1], cells[2]
        link = ""
        notes = " ".join(cells[3:])
        for cell in cells:
            if match := LINK_RE.search(cell):
                link = match.group(2)
                if not role or role.lower() in {"apply", "link"}:
                    role = match.group(1)
                break
            if "http" in cell:
                link = cell.split()[0]
                break
        if company and role and link:
            jobs.append(
                {
                    "company": re.sub(r"\[|\].*", "", company).strip(),
                    "title": re.sub(r"\[|\].*", "", role).strip(),
                    "location": location,
                    "apply_url": link,
                    "notes": notes,
                    "source_url": source_url,
                }
            )
    return jobs


class GitHubListsAdapter:
    name = "github_lists"
    source_type = "github_markdown"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def validate_config(self) -> SourceHealth:
        repos = self.config.get("repos") or []
        return SourceHealth(ok=True, status="ok", message=f"{len(repos)} markdown list(s) configured.")

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        payloads: list[RawJob] = []
        if query.demo:
            markdown = load_fixture_text("github_internship_readme.md")
            rows = parse_markdown_jobs(markdown, "fixture://github_lists")
            return [RawJob(source=self.name, payload=row, source_url="fixture://github_lists") for row in rows[: query.max_results]]

        for repo in self.config.get("repos") or []:
            markdown = ""
            for url in self._raw_candidates(repo):
                try:
                    markdown = fetch_text(url)
                    break
                except requests.HTTPError as exc:
                    if exc.response is None or exc.response.status_code != 404:
                        raise
            if not markdown:
                continue
            for row in parse_markdown_jobs(markdown, repo)[: query.max_results]:
                parsed = urlparse(repo)
                payloads.append(RawJob(source=self.name, payload={**row, "repo": parsed.path.strip("/")}, source_url=repo))
        return payloads

    def _raw_candidates(self, repo: str) -> list[str]:
        match = GITHUB_REPO_RE.match(repo.strip())
        if not match:
            return [github_raw_url(repo)]
        owner, name = match.groups()
        return [
            github_raw_url(repo),
            f"https://raw.githubusercontent.com/{owner}/{name}/dev/README.md",
            f"https://raw.githubusercontent.com/{owner}/{name}/master/README.md",
        ]

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        title = item.get("title", "")
        notes = item.get("notes", "")
        return JobCreate(
            title=title,
            company=item.get("company", ""),
            location=item.get("location", ""),
            remote_type=infer_remote_type(notes, item.get("location", "")),
            employment_type=infer_employment_type(title, notes),
            internship_flag="intern" in title.lower() or "intern" in notes.lower(),
            description=notes,
            source=self.name,
            source_job_id=item.get("apply_url", ""),
            source_url=raw.source_url or item.get("source_url", ""),
            apply_url=item.get("apply_url", ""),
            raw=item,
            metadata={"repo": item.get("repo", "")},
        )

    def supports_apply(self) -> bool:
        return False
