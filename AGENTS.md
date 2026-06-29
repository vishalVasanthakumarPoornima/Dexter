# Dexter Agent Notes

Dexter is a local-first personal assistant. Jobs OS work must stay safe-by-default:

- Do not store credentials, browser cookies, or private application answers in source code.
- Do not auto-submit external applications.
- Keep LinkedIn, Indeed, Glassdoor, Handshake, and similar platforms manual-only or supervised.
- Use fixture/demo mode for tests; do not rely on live APIs in the normal suite.
- Generated job databases, reports, screenshots, raw payloads, and browser profiles are runtime artifacts and should not be staged.

Primary Jobs OS commands:

```bash
python -m backend.app.jobs.cli run-daily --demo
python -m backend.app.jobs.cli ingest --source all
python -m backend.app.jobs.cli score
python -m backend.app.jobs.cli generate-packets
python -m backend.app.jobs.cli report
python -m backend.app.jobs.cli apply-session --job-id <id> --demo
```
