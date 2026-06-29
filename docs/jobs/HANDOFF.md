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

Known local runtime artifacts:

- `data/jobs/jobs.sqlite3`
- `data/generated/application_packets/`
- `data/raw_payloads/`
- `data/reports/`
- `data/screenshots/`

These are ignored by git.

Next exact steps:

1. Copy `config/jobs.example.yaml` to local-only `config/jobs.yaml` if it does not exist.
2. Add target company board tokens in `config/jobs.yaml`.
3. Add API keys in `.env` for USAJOBS and Adzuna if desired.
4. Run `python -m backend.app.jobs.cli run-daily`.
5. Review the Jobs dashboard approval queue.
