from __future__ import annotations

import json
from pathlib import Path

from backend.jobs.config import PROJECT_ROOT


def legacy_inventory() -> dict:
    job_runs = list((PROJECT_ROOT / "logs" / "job_agent_runs").glob("*.json"))
    automation_runs = list((PROJECT_ROOT / "logs" / "job_automation_runs").glob("*.json"))
    automation_config = PROJECT_ROOT / "data" / "job_automations" / "automations.json"
    automations = {}
    if automation_config.exists():
        try:
            automations = json.loads(automation_config.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            automations = {}
    return {
        "job_runs": len(job_runs),
        "automation_runs": len(automation_runs),
        "automations": len(automations) if isinstance(automations, dict) else 0,
        "job_run_files": [str(path) for path in sorted(job_runs)[-10:]],
        "automation_run_files": [str(path) for path in sorted(automation_runs)[-10:]],
        "note": "Legacy files are inventoried but not deleted. Jobs OS writes new normalized state to SQLite.",
    }
