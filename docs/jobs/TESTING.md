# Jobs OS Testing

Backend:

```bash
python -m unittest tests.test_jobs_os
python -m unittest tests.test_jobs_api
python -m unittest discover -s tests
```

Frontend:

```bash
cd frontend/dashboard
npm run lint
/Users/vasanth/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/typescript/bin/tsc -b
/Users/vasanth/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/vite/bin/vite.js build
```

Demo:

```bash
python -m backend.app.jobs.cli run-daily --demo
python -m backend.app.jobs.cli apply-session --job-id 1 --demo
```

Normal tests use fixtures under `tests/fixtures/jobs/` and do not call live job APIs.
