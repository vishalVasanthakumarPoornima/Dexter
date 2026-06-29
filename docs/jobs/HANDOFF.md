# Jobs OS Handoff

Built:

- Backend Jobs OS package under `backend/jobs`.
- Profile helpers under `backend/profile`.
- Notification fallback stubs under `backend/notifications`.
- API routes under `backend/api/jobs.py`.
- CLI under `backend/jobs/cli.py` and compatibility wrapper under `backend/app/jobs/cli.py`.
- Jobs dashboard under `frontend/dashboard/src/pages/JobsPage.tsx`.
- Demo fixtures under `tests/fixtures/jobs`.
- Tests under `tests/test_jobs_os.py` and `tests/test_jobs_api.py`.
- Expanded source adapters for Ashby, SmartRecruiters, Recruitee, The Muse, Arbeitnow, Careerjet, Jooble, and Brave Search.
- `.env` loading now preserves explicit process env overrides, so test/demo commands can isolate `DEXTER_JOBS_DB_URL`.
- Structured live-search controls now drive backend filtering for role, term, cohort year, date posted, employment type, source, score, and work mode.
- Bulk Open is handled by a local backend endpoint and reports open failures instead of relying on fragile frontend popup behavior.
- Approval now generates a per-job `tailored_resume_draft.md` artifact plus resume suggestions and a cover-letter draft; the base resume is not modified.
- Download Resume streams a temporary one-sided Jake's Resume LaTeX export through the browser download/save flow instead of only saving inside the Dexter repo.
- `/api/jobs/overview` is read-only now; source-health writes were moved out of that hot path to avoid SQLite `database is locked` failures during concurrent Jobs requests.

Known local runtime artifacts:

- `data/jobs/jobs.sqlite3`
- `data/generated/application_packets/`
- `data/raw_payloads/`
- `data/reports/`
- `data/screenshots/`

These are ignored by git.

Next exact steps:

1. Copy `config/jobs.example.yaml` to local-only `config/jobs.yaml` if it does not exist.
2. Add target company board identifiers in `config/jobs.yaml` for Greenhouse, Lever, Ashby, SmartRecruiters, and Recruitee.
3. Add API keys in `.env` for USAJOBS, Adzuna, Careerjet, Jooble, or Brave Search if desired.
4. Run `python -m backend.app.jobs.cli run-daily`.
5. Review the Jobs dashboard approval queue.
