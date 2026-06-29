from __future__ import annotations

from typing import Any

from backend.tools.registry import execute_registered_tool, resolve_tool_name
from backend.utils.logger import log_action


def _legacy_plan_to_step(plan: dict[str, Any]) -> dict[str, Any]:
    action = resolve_tool_name(plan.get("action", ""))

    arg_map = {
        "read_file": {"path": plan.get("path")},
        "search_files": {"query": plan.get("query"), "root": plan.get("root")},
        "run_command": {"command": plan.get("command")},
        "open_app": {"app": plan.get("app")},
        "close_app": {"app": plan.get("app")},
        "list_apps": {},
        "spotify_search": {"query": plan.get("query")},
        "brave_search": {"query": plan.get("query")},
        "web_search": {
            "query": plan.get("query"),
            "max_results": plan.get("max_results"),
        },
    }

    return {
        "id": "step_1",
        "tool": action,
        "args": {
            key: value
            for key, value in arg_map.get(action, {}).items()
            if value is not None
        },
        "purpose": plan.get("reason") or plan.get("purpose") or action,
    }


def _normalize_steps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    raw_steps = plan.get("steps")

    if not raw_steps and plan.get("action") not in (None, "chat"):
        raw_steps = [_legacy_plan_to_step(plan)]

    steps: list[dict[str, Any]] = []

    for index, raw_step in enumerate(raw_steps or [], start=1):
        tool_name = resolve_tool_name(
            raw_step.get("tool") or raw_step.get("action") or ""
        )

        if not tool_name or tool_name == "chat":
            continue

        steps.append(
            {
                "id": raw_step.get("id") or f"step_{index}",
                "tool": tool_name,
                "args": raw_step.get("args") or {},
                "purpose": raw_step.get("purpose") or raw_step.get("reason") or "",
                "continue_on_error": bool(raw_step.get("continue_on_error", False)),
            }
        )

    return steps


def _stringify_result(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return str(result)

    if result.get("output"):
        return str(result["output"])

    if result.get("content"):
        return str(result["content"])

    if result.get("results"):
        lines = []
        for index, item in enumerate(result.get("results", [])[:8], start=1):
            if isinstance(item, dict):
                lines.append(
                    f"{index}. {item.get('title', '')}\n"
                    f"{item.get('snippet', '')}\n"
                    f"{item.get('url', '')}"
                )
            else:
                lines.append(f"{index}. {item}")
        return "\n\n".join(lines)

    return str(result)


def _inject_previous_results(
    step: dict[str, Any],
    executed_steps: list[dict[str, Any]],
) -> dict[str, Any]:
    if not executed_steps:
        return step

    args = dict(step.get("args") or {})
    previous_text = "\n\n".join(
        _stringify_result(item.get("result", {}))
        for item in executed_steps
        if item.get("result", {}).get("ok")
    ).strip()

    if not previous_text:
        return step

    tool = step.get("tool")

    if tool == "file_controller" and args.get("action") in {"write", "create_file"}:
        if not args.get("content"):
            args["content"] = previous_text

    if tool == "send_message" and not args.get("message_text"):
        args["message_text"] = previous_text[:2000]

    if tool == "code_helper" and args.get("action") in {"write", "edit"} and not args.get("description"):
        args["description"] = previous_text[:2000]

    return {**step, "args": args}


def execute_plan(plan: dict[str, Any]) -> dict[str, Any]:
    steps = _normalize_steps(plan)

    if not steps:
        return {
            "ok": True,
            "mode": "chat",
            "plan": plan,
            "steps": [],
        }

    executed_steps = []
    all_ok = True

    for step in steps:
        step = _inject_previous_results(step, executed_steps)
        result = execute_registered_tool(step["tool"], step.get("args", {}))
        step_result = {
            "id": step["id"],
            "tool": step["tool"],
            "args": step.get("args", {}),
            "purpose": step.get("purpose", ""),
            "ok": bool(result.get("ok")),
            "result": result,
        }
        executed_steps.append(step_result)

        log_action("tool_step_execution", step_result)

        if not result.get("ok"):
            all_ok = False
            if not step.get("continue_on_error"):
                break

    execution_result = {
        "ok": all_ok,
        "mode": "tools",
        "plan": plan,
        "steps": executed_steps,
    }

    log_action("tool_plan_execution", execution_result)
    return execution_result


def execute_tool(plan: dict[str, Any]) -> dict[str, Any]:
    execution = execute_plan(plan)
    steps = execution.get("steps", [])

    if not steps:
        return {"ok": False, "error": "No tool step to execute."}

    return steps[-1].get("result", {"ok": False, "error": "No result returned."})
