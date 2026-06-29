from __future__ import annotations

from backend.jobs.adapters.base import JobCreate, RawJob, SourceHealth
from backend.jobs.adapters.common import clean_html, fetch_json, first, infer_employment_type, load_fixture_json, parse_datetime
from backend.jobs.schemas import JobQuery


class SmartRecruitersAdapter:
    name = "smartrecruiters"
    source_type = "ats"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def _companies(self) -> list[str]:
        return [str(company).strip() for company in self.config.get("companies", []) if str(company).strip()]

    def validate_config(self) -> SourceHealth:
        companies = self._companies()
        return SourceHealth(ok=True, status="ok", message=f"{len(companies)} SmartRecruiters company identifier(s) configured; no key required.")

    def fetch_jobs(self, query: JobQuery) -> list[RawJob]:
        if query.demo:
            payload = load_fixture_json("smartrecruiters_postings.json")
            return [RawJob(source=self.name, payload=item, source_url="fixture://smartrecruiters") for item in payload.get("content", [])[: query.max_results]]

        jobs: list[RawJob] = []
        for company in self._companies():
            url = f"https://api.smartrecruiters.com/v1/companies/{company}/postings?limit={min(query.max_results or 100, 100)}"
            payload = fetch_json(url)
            for item in payload.get("content", [])[: query.max_results]:
                detail_url = item.get("ref") or f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{item.get('id')}"
                try:
                    item = fetch_json(detail_url)
                except Exception:
                    item = {**item, "detail_error": "detail_fetch_failed"}
                jobs.append(RawJob(source=self.name, payload=item, source_url=detail_url))
        return jobs

    def normalize(self, raw: RawJob) -> JobCreate:
        item = raw.payload
        title = first(item.get("name"))
        company = item.get("company") if isinstance(item.get("company"), dict) else {}
        location_data = item.get("location") if isinstance(item.get("location"), dict) else {}
        sections = ((item.get("jobAd") or {}).get("sections") or {}) if isinstance(item.get("jobAd"), dict) else {}
        section_texts = []
        for section in sections.values():
            if isinstance(section, dict):
                section_texts.append(clean_html(first(section.get("text"))))
        description = " ".join(text for text in section_texts if text)
        if not description:
            description = clean_html(first(item.get("description") or item.get("jobAd", {}).get("text") if isinstance(item.get("jobAd"), dict) else ""))
        type_of_employment = item.get("typeOfEmployment") if isinstance(item.get("typeOfEmployment"), dict) else {}
        remote_type = "remote" if location_data.get("remote") else "hybrid" if location_data.get("hybrid") else "onsite"
        return JobCreate(
            title=title,
            company=first(company.get("name") or company.get("identifier") or "Unknown Company"),
            location=first(location_data.get("fullLocation") or location_data.get("city") or location_data.get("country")),
            remote_type=remote_type,
            employment_type=infer_employment_type(title, first(type_of_employment.get("label") or description)),
            internship_flag="intern" in f"{title} {description}".lower(),
            description=description,
            source=self.name,
            source_job_id=first(item.get("id") or item.get("uuid") or item.get("postingUrl")),
            source_url=first(item.get("postingUrl") or raw.source_url),
            apply_url=first(item.get("applyUrl") or item.get("postingUrl")),
            date_posted=parse_datetime(item.get("releasedDate")),
            raw=item,
            manual_required=True,
            metadata={
                "department": item.get("department"),
                "function": item.get("function"),
                "experience_level": item.get("experienceLevel"),
                "type_of_employment": type_of_employment,
            },
        )

    def supports_apply(self) -> bool:
        return False
