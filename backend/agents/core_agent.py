import json
import os

from backend.memory.qdrant_memory import store_memory, query_memory
from backend.models.ollama_client import chat_with_ollama, summarize_tool_results
from backend.utils.logger import log_action

from backend.agents.planner import determine_plan, normalize_plan
from backend.agents.tool_executor import execute_plan


def _format_tool_response(plan: dict, result: dict) -> str:
    action = plan.get("action")

    if action == "read_file":
        if result.get("ok"):
            return (
                f"Read file: {result.get('path')}\n\n"
                f"{result.get('content', '')}"
            )
        return f"Could not read file: {result.get('error')}"

    if action == "search_files":
        matches = result.get("matches", [])
        if not matches:
            return f"No files found for query: {plan.get('query')}"

        formatted = "\n".join(f"- {match}" for match in matches)
        return f"Found {len(matches)} result(s) for '{plan.get('query')}':\n{formatted}"

    if action == "terminal":
        if result.get("ok"):
            return (
                f"Command executed: {result.get('command')}\n\n"
                f"{result.get('output', '')}"
            )
        return (
            f"Command not executed: {result.get('command')}\n\n"
            f"{result.get('error', '')}"
        )
    if action == "open_app":
        if result.get("ok"):
            return result.get("output", "App opened.")
        return f"Could not open app: {result.get('error')}"

    if action == "list_apps":
        if result.get("ok"):
            apps = result.get("apps", [])
            return "Installed apps:\n" + "\n".join(f"- {app}" for app in apps)
        return f"Could not list apps: {result.get('error')}"

    if action == "close_app":
        if result.get("ok"):
            return result.get("output", "App closed.")
        return f"Could not close app: {result.get('error')}"

    if action == "spotify_search":
        if result.get("ok"):
            return result.get("output", "Spotify search opened.")
        return f"Spotify search failed: {result.get('error')}"

    if action == "brave_search":
        if result.get("ok"):
            return result.get("output", "Brave search opened.")
        return f"Brave search failed: {result.get('error')}"

    if action == "web_search":
        if not result.get("ok"):
            return f"Web search failed: {result.get('error')}"

        results = result.get("results", [])
        if not results:
            return f"No web results found for: {plan.get('query')}"

        lines = []
        for idx, item in enumerate(results, start=1):
            lines.append(
                f"{idx}. {item.get('title')}\n"
                f"   {item.get('snippet')}\n"
                f"   {item.get('url')}"
            )

        return "Web results:\n" + "\n\n".join(lines)

    return str(result)


def _format_execution_response(execution_result: dict) -> str:
    steps = execution_result.get("steps", [])

    if not steps:
        return "Done."

    lines = []

    for step in steps:
        result = step.get("result", {})
        tool = step.get("tool", "tool")

        if result.get("ok"):
            if result.get("output"):
                lines.append(result.get("output", f"{tool} completed."))
            elif tool in {"open_app", "close_app", "spotify_search", "brave_search"}:
                lines.append(result.get("output", f"{tool} completed."))
            elif tool == "web_search":
                items = result.get("results", [])
                lines.append(f"Found {len(items)} web result(s) for {result.get('query')}.")
            elif tool == "read_file":
                lines.append(
                    f"Read {result.get('path')}:\n{result.get('content', '')[:1200]}"
                )
            elif tool == "search_files":
                matches = result.get("matches", [])
                lines.append(f"Found {len(matches)} matching file(s): " + ", ".join(matches[:8]))
            elif tool == "list_apps":
                apps = result.get("apps", [])
                lines.append(f"Found {len(apps)} installed app(s).")
            elif tool == "run_command":
                lines.append(result.get("output", "Command completed."))
            elif tool == "file_controller":
                items = result.get("items") or result.get("matches") or result.get("files")
                if items:
                    lines.append(f"{tool} returned {len(items)} item(s).")
                else:
                    lines.append("File action completed.")
            elif tool == "audit_tools":
                lines.append(
                    "Tool audit complete: "
                    f"{result.get('passed', 0)} safe smoke test(s) passed, "
                    f"{result.get('skipped', 0)} side-effect tool(s) skipped, "
                    f"{result.get('failed', 0)} failed."
                )
            elif tool in {
                "weather_report",
                "youtube_video",
                "browser_control",
                "computer_settings",
                "computer_control",
                "desktop_control",
                "screen_process",
                "reminder",
                "flight_finder",
                "game_updater",
                "file_processor",
                "code_helper",
                "dev_agent",
                "job_application_agent",
                "job_automation_agent",
                "send_resume_whatsapp",
            }:
                lines.append(f"{tool} completed.")
            else:
                lines.append(str(result))
        else:
            lines.append(f"{tool} failed: {result.get('error', 'Unknown error')}")

    return "\n".join(line for line in lines if line)


def _plan_from_model_tool_json(response: str, message: str) -> dict | None:
    text = (response or "").strip()
    if not text.startswith(("{", "[")):
        return None

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None

    if isinstance(payload, list):
        raw_plan = {"mode": "tools", "steps": payload}
    elif isinstance(payload, dict):
        if payload.get("steps") or payload.get("action") or payload.get("tool"):
            raw_plan = payload
            if payload.get("tool") and not payload.get("steps"):
                raw_plan = {"mode": "tools", "steps": [payload]}
        else:
            return None
    else:
        return None

    plan = normalize_plan(raw_plan, source="model_tool_json", message=message)
    return plan if plan.get("requires_tools") else None


def run_agent(message: str) -> str:
    store_memory(message, metadata={"source": "chat"})

    top_memories = query_memory(message, top_k=5)
    memory_texts = [
        memory["text"]
        for memory in top_memories
        if memory.get("text") and memory["text"] != message
    ]

    memory_context = "\n".join(f"- {m}" for m in memory_texts)

    plan = determine_plan(message, memory_context=memory_context)

    if plan.get("requires_tools"):
        execution_result = execute_plan(plan)
        fast_tool_responses = os.getenv(
            "DEXTER_FAST_TOOL_RESPONSES",
            "true",
        ).lower() in {"1", "true", "yes"}

        if fast_tool_responses:
            response = _format_execution_response(execution_result)
        else:
            response = summarize_tool_results(
                user_message=message,
                execution_result=execution_result,
                memory_context=memory_context,
            )

        if response.startswith(("Ollama error:", "LLM error:")):
            response = _format_execution_response(execution_result)

        store_memory(response, metadata={"source": "dexter_response"})

        log_action(
            "agent_plan_execution",
            {
                "input": message,
                "plan": plan,
                "execution": execution_result,
                "response": response,
            },
        )

        return response

    response = chat_with_ollama(
        user_message=message,
        memory_context=memory_context,
    )

    fallback_plan = _plan_from_model_tool_json(response, message)
    if fallback_plan:
        execution_result = execute_plan(fallback_plan)
        response = _format_execution_response(execution_result)
        log_action(
            "agent_model_tool_json_execution",
            {
                "input": message,
                "plan": fallback_plan,
                "execution": execution_result,
                "response": response,
            },
        )

    store_memory(response, metadata={"source": "dexter_response"})

    log_action(
        "chat",
        {
            "input": message,
            "response": response,
        },
    )

    return response
