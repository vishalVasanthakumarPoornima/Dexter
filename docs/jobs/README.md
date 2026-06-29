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

Demo mode uses fixtures and requires no API keys:

```bash
python -m backend.app.jobs.cli ingest --source all --demo
python -m backend.app.jobs.cli run-daily --demo
python -m backend.app.jobs.cli apply-session --job-id 1 --demo
```
