# Dexter Jobs OS Task Map

## Done

- SQLite-backed Jobs OS schema.
- Source adapters for Greenhouse, Lever, USAJOBS, Adzuna, Remotive, GitHub lists, RSS, manual links, company career discovery, web discovery, and restricted/manual links.
- Fixture-backed demo mode.
- Normalization and dedupe.
- Transparent scoring.
- Application packet generation.
- Approval queue records.
- Fake-form supervised apply sessions that stop before final submit.
- Jobs API routes under `/api/jobs`.
- Jobs dashboard tab.
- CLI wrapper at `python -m backend.app.jobs.cli`.
- Markdown/JSON report generation.
- Backend tests for service, adapters, policy, API, and fake-form behavior.

## Next

- Add deeper live Greenhouse/Lever company catalogs.
- Add source-specific rate limiting and ETag caching.
- Add real Playwright fill actions for selected ATS pages after more supervised testing.
- Add frontend E2E screenshots and visual regression.
- Add optional WhatsApp/email providers for report delivery.
