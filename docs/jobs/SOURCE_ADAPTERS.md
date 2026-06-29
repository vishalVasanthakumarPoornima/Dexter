# Source Adapters

Adapters implement a shared contract: validate config, fetch raw jobs, normalize to Jobs OS, report apply support, and operate in dry-run/demo mode.

Supported adapters:

- Greenhouse: public board-token API, no submit.
- Lever: public postings API by site slug, no submit.
- USAJOBS: official API behind `USAJOBS_API_KEY` and `USAJOBS_EMAIL`.
- Adzuna: API behind `ADZUNA_APP_ID` and `ADZUNA_APP_KEY`.
- Remotive: public remote jobs API.
- GitHub lists: markdown tables and Vansh/Simplify-style internship lists.
- RSS: RSS/Atom job feeds.
- Manual link: user-pasted job URLs.
- Company careers: shallow ATS/career link discovery.
- Web discovery: search-query candidates routed to manual review.
- Restricted manual: LinkedIn, Indeed, Glassdoor, and similar sources as manual-only links.

Add a new source by creating `backend/jobs/adapters/<source>.py`, registering it in `backend/jobs/adapters/__init__.py`, and adding fixture tests.
