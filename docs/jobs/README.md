# Dexter Jobs OS

Run demo mode first:

```bash
cp config/jobs.example.yaml config/jobs.yaml
python -m backend.app.jobs.cli run-daily --demo
./start.sh
```

Open the dashboard at `http://127.0.0.1:5173` and select the Jobs tab.

Core workflow:

```bash
python -m backend.app.jobs.cli ingest --source all
python -m backend.app.jobs.cli score
python -m backend.app.jobs.cli generate-packets
python -m backend.app.jobs.cli report
```

No-key live sources available immediately:

- Remotive
- The Muse
- Arbeitnow
- Greenhouse/Lever/Ashby/SmartRecruiters/Recruitee after you add company board identifiers
- GitHub lists
- RSS feeds

Key-gated optional sources:

- USAJOBS: `USAJOBS_API_KEY`, `USAJOBS_EMAIL`
- Adzuna: `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`
- Careerjet: `CAREERJET_API_KEY`
- Jooble: `JOOBLE_API_KEY`
- Brave Search: `BRAVE_SEARCH_API_KEY`

Demo mode uses fixtures and requires no API keys:

```bash
python -m backend.app.jobs.cli ingest --source all --demo
python -m backend.app.jobs.cli run-daily --demo
python -m backend.app.jobs.cli apply-session --job-id 1 --demo
```
