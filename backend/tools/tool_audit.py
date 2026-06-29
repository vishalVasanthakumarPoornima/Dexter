from __future__ import annotations

import importlib
from typing import Any

from backend.tools.registry import TOOL_SPECS, execute_registered_tool


SAFE_SMOKE_ARGS: dict[str, dict[str, Any]] = {
    "read_file": {"path": "backend/main.py"},
    "search_files": {"query": "Dexter", "root": "project", "max_results": 5},
    "run_command": {"command": "pwd"},
    "list_apps": {},
    "browser_agent": {"action": "status"},
    "file_controller": {"action": "list", "path": "project"},
    "send_message": {
        "receiver": "Dexter Audit",
        "message_text": "Dexter messaging dry run.",
        "platform": "whatsapp",
        "dry_run": True,
    },
    "job_application_agent": {"action": "status", "open_browser": False},
}

SIDE_EFFECT_TOOLS = {
    "open_app",
    "close_app",
    "spotify_search",
    "brave_search",
    "web_search",
    "weather_report",
    "youtube_video",
    "browser_control",
    "computer_settings",
    "computer_control",
    "desktop_control",
    "screen_process",
    "send_resume_whatsapp",
    "reminder",
    "flight_finder",
    "game_updater",
    "file_processor",
    "code_helper",
    "dev_agent",
}


def _handler_import_ok(handler_path: str) -> tuple[bool, str]:
    try:
        module_name, function_name = handler_path.split(":", 1)
        module = importlib.import_module(module_name)
        getattr(module, function_name)
        return True, ""
    except Exception as e:
        return False, str(e)


def audit_tools(include_side_effects: bool = False) -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    for name, spec in TOOL_SPECS.items():
        handler_ok, handler_error = _handler_import_ok(spec.handler)
        entry: dict[str, Any] = {
            "tool": name,
            "enabled": spec.enabled,
            "handler_ok": handler_ok,
            "smoke_status": "not_run",
        }

        if handler_error:
            entry["handler_error"] = handler_error
            entry["ok"] = False
            results.append(entry)
            continue

        if name in SAFE_SMOKE_ARGS:
            smoke = execute_registered_tool(name, SAFE_SMOKE_ARGS[name])
            entry["smoke_status"] = "passed" if smoke.get("ok") else "failed"
            entry["ok"] = bool(smoke.get("ok"))
            entry["summary"] = smoke.get("output") or smoke.get("error") or "Smoke test completed."
        elif name in SIDE_EFFECT_TOOLS and not include_side_effects:
            entry["smoke_status"] = "skipped_side_effect"
            entry["ok"] = True
            entry["summary"] = "Registered and importable; live run skipped to avoid side effects."
        else:
            entry["ok"] = handler_ok
            entry["summary"] = "Registered and importable."

        results.append(entry)

    failed = [item for item in results if not item.get("ok")]
    passed = [item for item in results if item.get("smoke_status") == "passed"]
    skipped = [item for item in results if str(item.get("smoke_status", "")).startswith("skipped")]

    return {
        "ok": not failed,
        "tool": "audit_tools",
        "total": len(results),
        "passed": len(passed),
        "skipped": len(skipped),
        "failed": len(failed),
        "results": results,
    }
