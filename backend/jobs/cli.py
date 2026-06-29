from __future__ import annotations

import argparse
import json

from backend.env import load_env
from backend.jobs.db import init_db
from backend.jobs.migration import legacy_inventory
from backend.jobs.reports import generate_daily_report
from backend.jobs.schemas import JobQuery
from backend.jobs.service import (
    generate_packets,
    ingest_jobs,
    latest_report,
    run_daily,
    score_jobs,
    start_apply_session,
)


def main(argv: list[str] | None = None) -> int:
    load_env()
    parser = argparse.ArgumentParser(description="Dexter Jobs OS CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Ingest jobs from adapters")
    ingest.add_argument("--source", default="all")
    ingest.add_argument("--keywords", default="Software Engineer Intern 2027")
    ingest.add_argument("--location", default="")
    ingest.add_argument("--demo", action="store_true")
    ingest.add_argument("--dry-run", action="store_true")

    score = sub.add_parser("score", help="Score ingested jobs")
    score.add_argument("--profile-id", type=int)

    packets = sub.add_parser("generate-packets", help="Generate application packets")
    packets.add_argument("--profile-id", type=int)
    packets.add_argument("--limit", type=int)
    packets.add_argument("--min-score", type=float, default=55.0)

    sub.add_parser("report", help="Generate latest report")
    daily = sub.add_parser("run-daily", help="Run ingest, score, packet, report")
    daily.add_argument("--demo", action="store_true")

    apply = sub.add_parser("apply-session", help="Create supervised apply session")
    apply.add_argument("--job-id", type=int, required=False)
    apply.add_argument("--demo", action="store_true")

    sub.add_parser("health", help="Show Jobs OS health")
    sub.add_parser("migrate", help="Inventory legacy job-run files")

    args = parser.parse_args(argv)
    init_db()

    if args.command == "ingest":
        result = ingest_jobs(
            source=args.source,
            query=JobQuery(keywords=args.keywords, location=args.location, demo=args.demo),
            demo=args.demo,
            dry_run=args.dry_run,
        )
    elif args.command == "score":
        result = score_jobs(profile_id=args.profile_id)
    elif args.command == "generate-packets":
        result = generate_packets(profile_id=args.profile_id, limit=args.limit, min_score=args.min_score)
    elif args.command == "report":
        from backend.jobs.db import get_session

        with get_session() as session:
            result = generate_daily_report(session)
            session.commit()
    elif args.command == "run-daily":
        result = run_daily(demo=args.demo)
    elif args.command == "apply-session":
        job_id = args.job_id
        if job_id is None:
            daily_result = run_daily(demo=True)
            top_jobs = daily_result.get("report", {}).get("jobs", [])
            job_id = top_jobs[0]["job_id"] if top_jobs else 1
        result = start_apply_session(job_id=job_id, demo=args.demo)
    elif args.command == "health":
        result = {"ok": True, "service": "jobs_os", "db_initialized": True, "latest_report": latest_report().get("ok", False)}
    elif args.command == "migrate":
        result = legacy_inventory()
    else:
        result = {"ok": False, "error": f"Unknown command: {args.command}"}

    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
