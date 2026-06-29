# Dexter Jobs OS Architecture

Dexter Jobs OS turns job discovery into a local, auditable pipeline:

1. Source adapters fetch raw postings or manual-review links.
2. Normalization maps each source into one job schema.
3. Dedupe creates a canonical job id from apply URL or company/title/location.
4. Scoring compares each job with the local application profile.
5. Packet generation creates resume suggestions, cover letter drafts, short answers, blockers, and recommendations.
6. Approvals gate every application action.
7. Supervised browser sessions can fill safe fields and must stop before final submit.
8. Reports and the dashboard show the current queue, source health, and run history.

Runtime state lives in SQLite at `data/jobs/jobs.sqlite3` by default. Large/auditable artifacts stay on disk:

- `data/raw_payloads/`
- `data/generated/`
- `data/screenshots/`
- `data/reports/`

The old `job_application_agent` and `job_automation_agent` tool names remain stable. They now route normal job searching into Jobs OS unless `DEXTER_JOBS_OS_LEGACY_LINKS=true`.
