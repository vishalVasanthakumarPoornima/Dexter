from __future__ import annotations

import json
import os
import plistlib
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.tools.job_agent import job_application_agent
from backend.utils.logger import log_action


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_DIR = Path(os.getenv("DEXTER_JOB_AUTOMATION_DIR", PROJECT_ROOT / "data" / "job_automations"))
CONFIG_PATH = AUTOMATION_DIR / "automations.json"
RUNS_DIR = Path(os.getenv("DEXTER_JOB_AUTOMATION_RUNS_DIR", PROJECT_ROOT / "logs" / "job_automation_runs"))
DEFAULT_AUTOMATION_ID = "morning_2027_cs_internships"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" .,!?:;\"'")


def _safe_id(value: str) -> str:
    clean = re.sub(r"[^a-z0-9_-]+", "_", value.lower()).strip("_")
    return clean[:80] or DEFAULT_AUTOMATION_ID


def _read_configs() -> dict[str, dict[str, Any]]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict):
        return {str(key): value for key, value in data.items() if isinstance(value, dict)}
    return {}


def _write_configs(configs: dict[str, dict[str, Any]]) -> None:
    AUTOMATION_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(configs, indent=2), encoding="utf-8")


def _default_query(query: str) -> str:
    clean_query = _clean(query)
    if clean_query:
        return clean_query
    return "find latest 2027 Software Engineer Internships for CS students from all sources"


def _parse_time(value: str) -> tuple[int, int]:
    clean = (value or "09:00").strip().lower()
    match = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", clean)
    if not match:
        return 9, 0
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    suffix = match.group(3)
    if suffix == "pm" and hour != 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    return max(0, min(hour, 23)), max(0, min(minute, 59))


def _launch_agent_paths(automation_id: str) -> tuple[str, Path, Path, Path]:
    label = f"com.dexter.job-automation.{automation_id}"
    launch_dir = Path.home() / "Library" / "LaunchAgents"
    stdout_path = RUNS_DIR / f"{automation_id}.out.log"
    stderr_path = RUNS_DIR / f"{automation_id}.err.log"
    return label, launch_dir / f"{label}.plist", stdout_path, stderr_path


def _install_launch_agent(config: dict[str, Any]) -> dict[str, Any]:
    automation_id = str(config["id"])
    hour, minute = _parse_time(str(config.get("time") or "09:00"))
    label, plist_path, stdout_path, stderr_path = _launch_agent_paths(automation_id)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    python_path = PROJECT_ROOT / ".venv" / "bin" / "python"
    if not python_path.exists():
        python_path = Path(os.getenv("PYTHON", "python3"))

    script_path = PROJECT_ROOT / "scripts" / "run_job_automation.py"
    plist = {
        "Label": label,
        "ProgramArguments": [
            str(python_path),
            str(script_path),
            "--id",
            automation_id,
            "--project-root",
            str(PROJECT_ROOT),
        ],
        "WorkingDirectory": str(PROJECT_ROOT),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(stdout_path),
        "StandardErrorPath": str(stderr_path),
        "RunAtLoad": False,
    }
    plist_path.write_bytes(plistlib.dumps(plist))

    loaded = False
    load_error = ""
    try:
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, text=True, timeout=8)
        completed = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True, timeout=8)
        loaded = completed.returncode == 0
        load_error = completed.stderr.strip()
    except Exception as e:
        load_error = str(e)

    return {
        "label": label,
        "plist_path": str(plist_path),
        "hour": hour,
        "minute": minute,
        "loaded": loaded,
        "load_error": load_error,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def _unload_launch_agent(automation_id: str) -> dict[str, Any]:
    label, plist_path, _, _ = _launch_agent_paths(automation_id)
    unloaded = False
    removed = False
    error = ""
    if plist_path.exists():
        try:
            completed = subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, text=True, timeout=8)
            unloaded = completed.returncode == 0
            error = completed.stderr.strip()
        except Exception as e:
            error = str(e)
        try:
            plist_path.unlink()
            removed = True
        except Exception as e:
            error = f"{error}; remove failed: {e}".strip("; ")
    return {"label": label, "plist_path": str(plist_path), "unloaded": unloaded, "removed": removed, "error": error}


def _save_run(automation_id: str, payload: dict[str, Any]) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RUNS_DIR / f"{timestamp}_{automation_id}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def run_automation_by_id(automation_id: str) -> dict[str, Any]:
    configs = _read_configs()
    config = configs.get(automation_id)
    if not config:
        return {"ok": False, "tool": "job_automation_agent", "error": f"Unknown job automation: {automation_id}"}
    if not config.get("enabled", True):
        return {"ok": False, "tool": "job_automation_agent", "error": f"Job automation is disabled: {automation_id}"}

    try:
        from backend.jobs.schemas import JobQuery
        from backend.jobs.service import generate_packets, ingest_jobs, latest_report, score_jobs

        demo_mode = os.getenv("DEXTER_JOBS_DEMO_MODE", "false").lower() in {"1", "true", "yes"}
        result = {
            "ok": True,
            "tool": "job_automation_agent",
            "mode": "jobs_os",
            "ingest": ingest_jobs(
                source=str(config.get("source_scope") or "all"),
                query=JobQuery(
                    keywords=str(config.get("query") or ""),
                    max_results=int(config.get("max_applications") or 10),
                    demo=demo_mode,
                ),
                demo=demo_mode,
            ),
            "scoring": score_jobs(),
            "packets": generate_packets(limit=int(config.get("max_applications") or 10)),
            "report": latest_report(),
            "output": "Jobs OS automation completed: ingest, score, packet, and local report. Final submit remains approval-gated.",
        }
    except Exception:
        result = job_application_agent(
            action="start",
            query=str(config.get("query") or ""),
            source_scope=str(config.get("source_scope") or "all"),
            max_applications=int(config.get("max_applications") or 10),
            auto_apply=bool(config.get("auto_apply_requested", False)),
            open_browser=bool(config.get("open_browser", True)),
            match_resume=bool(config.get("match_resume", True)),
            check_pages=True,
            brave_group=True,
            notes=str(config.get("notes") or "Scheduled internship automation run."),
        )
    payload = {
        "automation_id": automation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "result": result,
    }
    run_path = _save_run(automation_id, payload)
    log_action("job_automation_run", {**payload, "run_file": str(run_path)})
    output = result.get("output", "Job automation run completed.")
    return {
        "ok": bool(result.get("ok")),
        "tool": "job_automation_agent",
        "action": "run",
        "automation_id": automation_id,
        "run_file": str(run_path),
        "output": f"Ran job automation '{automation_id}'. {output}",
        "result": result,
    }


def job_automation_agent(
    action: str = "status",
    query: str = "",
    automation_id: str = DEFAULT_AUTOMATION_ID,
    time: str = "09:00",
    max_applications: int = 10,
    auto_apply_requested: bool = True,
    match_resume: bool = True,
    open_browser: bool = True,
    source_scope: str = "all",
    install_launch_agent: bool = True,
    notes: str = "",
) -> dict[str, Any]:
    clean_action = _clean(action).lower().replace("-", "_") or "status"
    clean_id = _safe_id(automation_id or DEFAULT_AUTOMATION_ID)
    configs = _read_configs()

    if clean_action in {"setup", "create", "enable", "start"}:
        config = {
            "id": clean_id,
            "enabled": True,
            "query": _default_query(query),
            "time": time or "09:00",
            "max_applications": max(1, min(int(max_applications or 10), 50)),
            "auto_apply_requested": bool(auto_apply_requested),
            "match_resume": bool(match_resume),
            "open_browser": bool(open_browser),
            "source_scope": source_scope or "all",
            "notes": notes,
            "created_at": configs.get(clean_id, {}).get("created_at") or datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "guardrails": {
                "final_submit_requires_user_review": True,
                "account_creation_requires_user_completion": True,
                "captcha_or_mfa": "manual",
                "resume_tailoring_pipeline": "not_implemented_yet",
                "application_submit": "review_checkpoint",
            },
        }
        launch_agent = _install_launch_agent(config) if install_launch_agent else {
            "loaded": False,
            "load_error": "",
            "plist_path": "",
        }
        config["launch_agent"] = launch_agent
        configs[clean_id] = config
        _write_configs(configs)
        output = (
            f"Set up job automation '{clean_id}' for {config['time']} every morning. "
            "It will scout 2027 CS/SWE internships and create review-ready job runs. "
            "Resume tailoring and final submission are still guarded behind manual review."
        )
        if install_launch_agent and not launch_agent.get("loaded"):
            output += " The LaunchAgent file was written, but launchctl did not confirm it loaded."
        return {
            "ok": True,
            "tool": "job_automation_agent",
            "action": "setup",
            "automation": config,
            "output": output,
        }

    if clean_action in {"run", "check", "run_now"}:
        return run_automation_by_id(clean_id)

    if clean_action in {"disable", "stop"}:
        config = configs.get(clean_id)
        if not config:
            return {"ok": False, "tool": "job_automation_agent", "error": f"Unknown job automation: {clean_id}"}
        config["enabled"] = False
        config["updated_at"] = datetime.now(timezone.utc).isoformat()
        config["launch_agent"] = {**config.get("launch_agent", {}), **_unload_launch_agent(clean_id)}
        configs[clean_id] = config
        _write_configs(configs)
        return {
            "ok": True,
            "tool": "job_automation_agent",
            "action": "disable",
            "automation": config,
            "output": f"Disabled job automation '{clean_id}'.",
        }

    if clean_action in {"status", "list", "latest"}:
        automations = list(configs.values())
        if not automations:
            return {
                "ok": True,
                "tool": "job_automation_agent",
                "action": clean_action,
                "automations": [],
                "output": "No job automations are configured yet.",
            }
        active = [item for item in automations if item.get("enabled", True)]
        output = f"{len(active)} active job automation(s): " + ", ".join(item["id"] for item in active)
        return {
            "ok": True,
            "tool": "job_automation_agent",
            "action": clean_action,
            "automations": automations,
            "output": output,
        }

    return {"ok": False, "tool": "job_automation_agent", "error": f"Unknown job automation action: {action}"}
