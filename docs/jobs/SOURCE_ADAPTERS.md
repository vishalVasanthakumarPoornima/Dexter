# Source Adapters

Adapters implement a shared contract: validate config, fetch raw jobs, normalize to Jobs OS, report apply support, and operate in dry-run/demo mode.

Supported adapters:

- Greenhouse: public board-token API, no submit.
- Lever: public postings API by site slug, no submit.
- USAJOBS: official API behind `USAJOBS_API_KEY` and `USAJOBS_EMAIL`.
- Adzuna: API behind `ADZUNA_APP_ID` and `ADZUNA_APP_KEY`.
- Remotive: public remote jobs API.
- Ashby: public job board API by board name, no key.
- SmartRecruiters: public postings API by company identifier, no key.
- Recruitee: public offers API by company subdomain, no key.
- The Muse: public jobs API, no key required; optional `THEMUSE_API_KEY` raises rate limits.
- Arbeitnow: free public job-board API, no key.
- Careerjet: search API behind `CAREERJET_API_KEY`.
- Jooble: API behind `JOOBLE_API_KEY`.
- Brave Search: search API behind `BRAVE_SEARCH_API_KEY`; produces manual-review discovery links.
- GitHub lists: markdown tables and Vansh/Simplify-style internship lists.
- RSS: RSS/Atom job feeds.
- Manual link: user-pasted job URLs.
- Company careers: shallow ATS/career link discovery.
- Web discovery: search-query candidates routed to manual review.
- Restricted manual: LinkedIn, Indeed, Glassdoor, and similar sources as manual-only links.

Add a new source by creating `backend/jobs/adapters/<source>.py`, registering it in `backend/jobs/adapters/__init__.py`, and adding fixture tests.

No-key ATS adapters still require identifiers:

- `ashby.boards`: Ashby board names from `jobs.ashbyhq.com/<board>`.
- `smartrecruiters.companies`: SmartRecruiters company identifiers from `jobs.smartrecruiters.com/<identifier>`.
- `recruitee.companies`: Recruitee subdomains from `<company>.recruitee.com`.

These identifiers are not secrets and can be added directly to `config/jobs.yaml`.
