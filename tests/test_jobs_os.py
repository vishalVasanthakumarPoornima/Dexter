import os
import tempfile
import unittest
from unittest.mock import patch

from backend.jobs.adapters.arbeitnow import ArbeitnowAdapter
from backend.jobs.adapters.ashby import AshbyAdapter
from backend.jobs.adapters.brave_search import BraveSearchAdapter
from backend.jobs.adapters.careerjet import CareerjetAdapter
from backend.jobs.adapters.github_lists import parse_markdown_jobs
from backend.jobs.adapters.jooble import JoobleAdapter
from backend.jobs.adapters.recruitee import RecruiteeAdapter
from backend.jobs.adapters.restricted_manual import RestrictedManualAdapter
from backend.jobs.adapters.smartrecruiters import SmartRecruitersAdapter
from backend.jobs.adapters.themuse import TheMuseAdapter
from backend.jobs.browser.form_analyzer import analyze_form_file
from backend.jobs.browser.form_filler import planned_field_values
from backend.jobs.db import reset_engine_for_tests
from backend.jobs.models import ApplicationProfile
from backend.jobs.schemas import JobQuery
from backend.jobs.service import (
    generate_packet_for_job,
    generate_packets,
    ingest_jobs,
    latest_report,
    list_jobs,
    run_daily,
    score_jobs,
    start_apply_session,
    submit_approved,
)


class JobsOSTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["DEXTER_JOBS_DB_URL"] = f"sqlite:///{self.tmp.name}/jobs.sqlite3"
        reset_engine_for_tests()

    def tearDown(self):
        reset_engine_for_tests()
        os.environ.pop("DEXTER_JOBS_DB_URL", None)
        self.tmp.cleanup()

    def test_demo_ingest_score_packets_report(self):
        ingest = ingest_jobs(source="all", query=JobQuery(keywords="Software Engineer Intern 2027", demo=True), demo=True)
        self.assertTrue(ingest["ok"])
        self.assertGreaterEqual(ingest["jobs_new"], 8)

        scoring = score_jobs()
        self.assertTrue(scoring["ok"])
        self.assertEqual(scoring["jobs_scored"], ingest["jobs_new"])

        packets = generate_packets(min_score=55)
        self.assertTrue(packets["ok"])
        self.assertGreater(packets["packets_generated"], 0)

        jobs = list_jobs(min_score=70)
        self.assertTrue(jobs["ok"])
        self.assertTrue(any(job["score"]["recommendation"] == "apply" for job in jobs["jobs"]))

        report = latest_report()
        self.assertTrue(report["ok"])
        self.assertIn("json_path", report)

    def test_run_daily_demo_is_vertical_slice(self):
        result = run_daily(demo=True)
        self.assertTrue(result["ok"])
        self.assertGreater(result["ingest"]["jobs_found"], 0)
        self.assertGreater(result["scoring"]["jobs_scored"], 0)
        self.assertIn("latest_markdown_path", result["report"])

    def test_generate_packet_for_one_job_and_submit_stays_disabled(self):
        run_daily(demo=True)
        jobs = list_jobs(min_score=70)["jobs"]
        packet = generate_packet_for_job(jobs[0]["id"])
        self.assertTrue(packet["ok"])
        self.assertIn("resume_variant_path", packet["packet"])

        submit = submit_approved(jobs[0]["id"])
        self.assertFalse(submit["ok"])
        self.assertIn("Auto-submit is disabled", submit["error"])

    def test_fake_apply_session_blocks_sensitive_fields(self):
        run_daily(demo=True)
        job_id = list_jobs(min_score=70)["jobs"][0]["id"]
        session = start_apply_session(job_id=job_id, demo=True)
        self.assertTrue(session["ok"])
        blocked_kinds = {field["kind"] for field in session["browser_session"]["fields_blocked"]}
        self.assertIn("work_authorization", blocked_kinds)
        self.assertIn("sponsorship", blocked_kinds)
        self.assertFalse(session["browser_session"]["metadata"]["final_submit_clicked"])

    def test_markdown_parser_extracts_internship_rows(self):
        markdown = "| Company | Role | Location | Application |\n| --- | --- | --- | --- |\n| A | SWE Intern | Remote | [Apply](https://example.com/a) |"
        rows = parse_markdown_jobs(markdown, "fixture://test")
        self.assertEqual(rows[0]["company"], "A")
        self.assertEqual(rows[0]["apply_url"], "https://example.com/a")

    def test_expanded_source_adapters_normalize_fixture_jobs(self):
        adapters = [
            AshbyAdapter(),
            SmartRecruitersAdapter(),
            RecruiteeAdapter(),
            TheMuseAdapter(),
            ArbeitnowAdapter(),
            CareerjetAdapter(),
            JoobleAdapter(),
            BraveSearchAdapter(),
        ]

        for adapter in adapters:
            with self.subTest(adapter=adapter.name):
                raw_jobs = adapter.fetch_jobs(JobQuery(demo=True, max_results=2))
                self.assertGreater(len(raw_jobs), 0)
                job = adapter.normalize(raw_jobs[0])
                self.assertTrue(job.title)
                self.assertTrue(job.apply_url)
                self.assertEqual(job.source, adapter.name)
                self.assertTrue(job.manual_required)

    def test_key_gated_sources_report_auth_required(self):
        with patch.dict(
            os.environ,
            {"CAREERJET_API_KEY": "", "JOOBLE_API_KEY": "", "BRAVE_SEARCH_API_KEY": ""},
        ):
            self.assertEqual(CareerjetAdapter().validate_config().status, "auth_required")
            self.assertEqual(JoobleAdapter().validate_config().status, "auth_required")
            self.assertEqual(BraveSearchAdapter().validate_config().status, "auth_required")

    def test_restricted_source_is_manual_only(self):
        adapter = RestrictedManualAdapter({"domains": ["linkedin.com"]})
        raw = adapter.fetch_jobs(JobQuery(keywords="https://www.linkedin.com/jobs/view/123"))
        self.assertEqual(len(raw), 1)
        job = adapter.normalize(raw[0])
        self.assertTrue(job.restricted)
        self.assertTrue(job.manual_required)
        self.assertFalse(adapter.supports_apply())

    def test_form_mapping_blocks_legal_fields(self):
        fields = analyze_form_file("tests/fixtures/jobs/sample_application_form.html")
        profile = ApplicationProfile(name="Vishal", email="v@example.com", phone="123", location="San Jose")
        filled, blocked = planned_field_values(fields, profile)
        self.assertTrue(any(field["kind"] == "email" for field in filled))
        self.assertTrue(any(field["kind"] == "sponsorship" for field in blocked))


if __name__ == "__main__":
    unittest.main()
