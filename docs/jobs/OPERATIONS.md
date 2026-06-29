# Jobs OS Operations

Start Dexter:

```bash
./start.sh
```

Health:

```bash
python -m backend.app.jobs.cli health
curl -s http://127.0.0.1:8000/api/jobs/overview
```

Daily local flow:

```bash
python -m backend.app.jobs.cli run-daily
```

Demo daily flow:

```bash
python -m backend.app.jobs.cli run-daily --demo
```

Reports:

- Markdown: `data/reports/latest_jobs_report.md`
- JSON: `data/reports/latest_jobs_report.json`

Runtime logs and artifacts are ignored by git. Review `data/raw_payloads/` when debugging source normalization.
