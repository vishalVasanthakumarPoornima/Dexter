import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.jobs.db import reset_engine_for_tests
from backend.main import app


class JobsAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["DEXTER_JOBS_DB_URL"] = f"sqlite:///{self.tmp.name}/jobs.sqlite3"
        reset_engine_for_tests()
        self.client = TestClient(app)

    def tearDown(self):
        reset_engine_for_tests()
        os.environ.pop("DEXTER_JOBS_DB_URL", None)
        self.tmp.cleanup()

    def test_jobs_api_demo_flow(self):
        ingest = self.client.post(
            "/api/jobs/ingest",
            json={
                "source": "all",
                "demo": True,
                "query": {"keywords": "Software Engineer Intern 2027", "demo": True, "max_results": 100},
            },
        )
        self.assertEqual(ingest.status_code, 200)
        self.assertTrue(ingest.json()["ok"])

        score = self.client.post("/api/jobs/score")
        self.assertEqual(score.status_code, 200)
        self.assertGreater(score.json()["jobs_scored"], 0)

        overview = self.client.get("/api/jobs/overview")
        self.assertEqual(overview.status_code, 200)
        self.assertGreater(overview.json()["metrics"]["total_jobs"], 0)

        jobs = self.client.get("/api/jobs?min_score=70")
        self.assertEqual(jobs.status_code, 200)
        job_id = jobs.json()["jobs"][0]["id"]

        packet = self.client.post(f"/api/jobs/{job_id}/packet", json={})
        self.assertEqual(packet.status_code, 200)
        self.assertTrue(packet.json()["ok"])

        apply = self.client.post(f"/api/jobs/{job_id}/apply-session?demo=true")
        self.assertEqual(apply.status_code, 200)
        self.assertFalse(apply.json()["browser_session"]["metadata"]["final_submit_clicked"])


if __name__ == "__main__":
    unittest.main()
