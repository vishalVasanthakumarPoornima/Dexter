from __future__ import annotations

import json
import os
import re
import urllib.parse
from typing import Any

from backend.models.ollama_client import DEFAULT_PLANNER_MODEL, chat_json_completion
from backend.tools.registry import get_tool, planner_tool_specs, resolve_tool_name

SAFE_DIRECT_COMMANDS = {
    "ls",
    "ls -la",
    "pwd",
    "whoami",
    "git status",
    "git branch",
    "git log --oneline -5",
    "find . -maxdepth 2 -type f",
}

MAX_PLAN_STEPS = int(os.getenv("DEXTER_MAX_PLAN_STEPS", "5"))

BROWSER_SITE_URLS = {
    "hollister": "https://www.hollisterco.com/shop/us",
    "hollisterco": "https://www.hollisterco.com/shop/us",
    "abercrombie": "https://www.abercrombie.com/shop/us",
    "target": "https://www.target.com",
    "walmart": "https://www.walmart.com",
    "best buy": "https://www.bestbuy.com",
    "bestbuy": "https://www.bestbuy.com",
    "netflix": "https://www.netflix.com",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "discord": "https://discord.com/channels/@me",
    "chatgpt": "https://chatgpt.com",
    "chat gpt": "https://chatgpt.com",
    "linkedin": "https://www.linkedin.com/jobs",
    "simplify": "https://simplify.jobs",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
}

BROWSER_ALIAS_ACTIONS = {
    "browser_navigate": "open_url",
    "browser_open": "open_url",
    "browser_goto": "open_url",
    "browser_go_to": "open_url",
    "browser_click": "click_text",
    "browser_type": "type",
    "browser_fill": "type",
    "browser_press": "press",
    "browser_scroll": "scroll",
    "browser_read": "inspect",
    "browser_inspect": "inspect",
}


def _llm_planner_disabled() -> bool:
    return os.getenv("DEXTER_DISABLE_LLM_PLANNER", "").lower() in {
        "1",
        "true",
        "yes",
    }


def _clean(text: str) -> str:
    return text.strip().strip(" .,!?:;\"'")


def _strip_prefix(message: str, prefixes: tuple[str, ...]) -> str:
    lower = message.lower().strip()

    for prefix in prefixes:
        if lower.startswith(prefix):
            return _clean(message[len(prefix) :])

    return _clean(message)


def _infer_max_price(message: str) -> float | None:
    match = re.search(
        r"\b(?:under|below|less than|max(?:imum)?|up to)\s+\$?\s*(\d+(?:\.\d{1,2})?)",
        message,
        re.I,
    )
    if not match:
        return None
    return float(match.group(1))


def _infer_shopping_query(message: str) -> str:
    lower = message.lower()
    known_products = (
        "reading glasses",
        "sunglasses",
        "laptop stand",
        "phone charger",
        "usb c cable",
        "keyboard",
        "mouse",
        "headphones",
    )
    for product in known_products:
        if product in lower:
            return product

    patterns = (
        r"(?:add|buy|find|search for|browse for|shop for)\s+(.+?)\s+(?:to\s+my\s+cart|on\s+amazon|under|below|less\s+than|max(?:imum)?|up\s+to|after\b)",
        r"(?:best|good)\s+(.+?)\s+(?:under|below|less\s+than|max(?:imum)?|up\s+to|on\s+amazon)",
    )
    for pattern in patterns:
        if match := re.search(pattern, message, re.I):
            query = _clean(match.group(1))
            query = re.sub(r"\b(?:best|one|item|product)\b", "", query, flags=re.I)
            query = re.sub(r"\s+", " ", query).strip()
            if query:
                return query

    return "reading glasses" if "glasses" in lower else _clean(message)


def _infer_browser_start_url(message: str) -> str:
    lower = message.lower()
    if match := re.search(r"https?://\S+", message):
        return match.group(0).rstrip(".,)")

    if "netflix" in lower:
        query = _infer_netflix_query(message)
        if query:
            return "https://www.netflix.com/search?q=" + urllib.parse.quote_plus(query)

    for site, url in BROWSER_SITE_URLS.items():
        if site in lower:
            return url

    if domain_match := re.search(r"\b([a-z0-9-]+\.(?:com|net|org|co|io|edu|gov))\b", lower):
        return "https://" + domain_match.group(1)

    return ""


def _infer_netflix_query(message: str) -> str:
    clean = re.split(r"\b(?:if|then|do not|don't|dont)\b", message, maxsplit=1, flags=re.I)[0]
    clean = re.sub(r"\bopen\s+netflix\s+and\s+", "", clean, flags=re.I)
    clean = re.sub(r"\b(?:on|in)\s+netflix\b", "", clean, flags=re.I)
    clean = re.sub(r"\bnetflix\b", "", clean, flags=re.I)
    clean = re.sub(r"\b(?:for\s+watching|and\s+start\s+playback|and\s+play\s+it|start\s+playback|playback)\b", "", clean, flags=re.I)

    if match := re.search(r"\b(?:open|play|start|watch|search(?:\s+for)?|find)\s+(.+)", clean, re.I):
        clean = match.group(1)

    return re.sub(r"\s+", " ", clean).strip(" .,!?:;\"'")


def _is_browser_workflow(message: str) -> bool:
    lower = message.lower()
    if ("whatsapp" in lower or "whats app" in lower) and "send" in lower:
        return False
    browser_verbs = (
        "add",
        "browse",
        "cart",
        "choose",
        "click",
        "find",
        "go to",
        "navigate",
        "open",
        "pick",
        "search",
        "select",
        "shop",
        "type",
    )
    site_named = bool(_infer_browser_start_url(message))
    return site_named and any(verb in lower for verb in browser_verbs)


def _browser_alias_action(raw_tool: str, args: dict[str, Any]) -> str:
    action = str(args.get("action") or "").strip()
    if action:
        return action

    alias_action = BROWSER_ALIAS_ACTIONS.get(raw_tool.strip())
    if alias_action:
        return alias_action

    if args.get("url"):
        return "open_url"
    if args.get("query"):
        return "search"
    if args.get("selector"):
        return "click_selector"
    if args.get("button_text") or args.get("text"):
        return "click_text"
    return "status"


def _canonical_app_name(app_name: str) -> str:
    clean = _clean(app_name)
    lower = clean.lower()

    aliases = {
        "brave": "Brave Browser",
        "brave browser": "Brave Browser",
        "browser": "Brave Browser",
        "spotify": "Spotify",
        "terminal": "Terminal",
        "notes": "Notes",
        "calendar": "Calendar",
        "messages": "Messages",
        "mail": "Mail",
        "safari": "Safari",
        "chrome": "Google Chrome",
        "google chrome": "Google Chrome",
    }

    return aliases.get(lower, clean)


def _message_platform(value: str) -> str:
    lower = value.lower().strip()
    if "whatsapp" in lower or "whats app" in lower:
        return "whatsapp"
    if "discord" in lower:
        return "discord"
    if lower in {"email", "mail", "mailto"} or "email" in lower:
        return "mailto"
    if lower in {"text", "sms", "imessage", "message", "messages"}:
        return "messages"
    return lower or "messages"


def _message_control_flags(message: str) -> tuple[bool, bool]:
    lower = message.lower()
    dry_run = any(
        phrase in lower
        for phrase in (
            "dry run",
            "dry-run",
            "test only",
            "validate only",
        )
    )
    auto_send = not dry_run and not any(
        phrase in lower
        for phrase in (
            "draft",
            "prepare",
            "review before sending",
            "let me review",
        )
    )
    return dry_run, auto_send


def _clean_message_body(body: str) -> str:
    cleaned = _clean(body)
    cleaned = re.sub(
        r"\s*,?\s*(?:dry[- ]run(?:\s+only)?|test only|do not send|don't send|dont send|without sending|no send|draft only|prepare only)\s*$",
        "",
        cleaned,
        flags=re.I,
    )
    return _clean(cleaned)


MESSAGE_PATTERNS = [
    r"(?:open\s+)?(?P<platform>whatsapp|whats\s+app|discord)\s+(?:and\s+)?send\s+(?:a\s+)?(?:text|message)\s+to\s+(?P<receiver>.+?)\s+(?:saying|that says|with|:)\s+(?P<body>.+)",
    r"send\s+(?:a\s+)?(?P<platform>text|sms)\s+to\s+(?P<receiver>.+?)\s+(?:saying|that says|with|:)\s+(?P<body>.+)",
    r"send\s+(?:a\s+)?(?P<platform>whatsapp|whats\s+app|imessage|sms|text|email|mail)\s+message\s+to\s+(?P<receiver>.+?)\s+(?:saying|that says|with|:)\s+(?P<body>.+)",
    r"send\s+(?:a\s+)?message\s+to\s+(?P<receiver>.+?)\s+(?:on|through|via)\s+(?P<platform>whatsapp|whats\s+app|imessage|sms|text|email|mail)\s+(?:saying|that says|with|:)\s+(?P<body>.+)",
    r"(?P<platform>whatsapp|whats\s+app|text|sms|email|mail)\s+(?P<receiver>.+?)\s+(?:saying|that says|with|:)\s+(?P<body>.+)",
    r"send\s+(?:a\s+)?message\s+to\s+(?P<receiver>.+?)\s+(?:saying|that says|with|:)\s+(?P<body>.+)",
]


def _message_plan_from_request(raw: str, message: str, error: str | None = None) -> dict[str, Any] | None:
    for pattern in MESSAGE_PATTERNS:
        if match := re.match(pattern, raw, re.I):
            groups = match.groupdict()
            first_word = raw.split(" ", 1)[0].lower()
            platform_text = groups.get("platform") or (
                first_word
                if first_word in {"whatsapp", "text", "sms", "email", "mail"}
                else "messages"
            )
            receiver = groups.get("receiver", "").strip()
            body = _clean_message_body(groups.get("body", ""))
            platform = _message_platform(platform_text)
            dry_run, auto_send = _message_control_flags(raw)
            if platform in {"discord"}:
                return _plan_from_steps(
                    [
                        _make_step(
                            "browser_task_agent",
                            {
                                "task": raw,
                                "start_url": _infer_browser_start_url(raw),
                                "max_steps": 18,
                                "allow_purchase": False,
                            },
                            "Use browser automation for this web messaging platform.",
                        )
                    ],
                    "heuristic",
                    message,
                    confidence=0.84,
                    response_style="detailed",
                    error=error,
                )

            return _plan_from_steps(
                [
                    _make_step(
                        "send_message",
                        {
                            "receiver": receiver,
                            "message_text": body,
                            "platform": platform,
                            "auto_send": auto_send,
                            **({"dry_run": True} if dry_run else {}),
                        },
                        "Send or prepare requested message.",
                    )
                ],
                "heuristic",
                message,
                confidence=0.9,
                error=error,
            )

    return None


def _resume_whatsapp_plan_from_request(raw: str, message: str, error: str | None = None) -> dict[str, Any] | None:
    lower = raw.lower()
    if "resume" not in lower or "send" not in lower:
        return None
    if "whatsapp" not in lower and "whats app" not in lower:
        return None

    receiver = ""
    patterns = [
        r"send\s+(?:my\s+|the\s+)?resume\s+to\s+(?P<receiver>.+?)\s+(?:through|via|on|using|over)\s+whats\s*app",
        r"send\s+(?:it|that|the\s+resume|my\s+resume)\s+to\s+(?P<receiver>.+?)\s+(?:through|via|on|using|over)\s+whats\s*app",
        r"find\s+(?:my\s+|the\s+)?resume.+?send\s+(?:it|that|the\s+resume|my\s+resume)?\s*to\s+(?P<receiver>.+?)\s+(?:through|via|on|using|over)\s+whats\s*app",
    ]
    for pattern in patterns:
        if match := re.search(pattern, raw, re.I):
            receiver = _clean(match.group("receiver"))
            break

    if not receiver:
        if match := re.search(r"\bto\s+(?P<receiver>.+?)\s+(?:through|via|on|using|over)\s+whats\s*app", raw, re.I):
            receiver = _clean(match.group("receiver"))

    if not receiver:
        return None

    dry_run, auto_send = _message_control_flags(raw)
    return _plan_from_steps(
        [
            _make_step(
                "send_resume_whatsapp",
                {
                    "receiver": receiver,
                    "query": "resume",
                    "root": "home",
                    "caption": "Here is my resume.",
                    "auto_send": auto_send,
                    **({"dry_run": True} if dry_run else {}),
                },
                "Find local resume and send it as a WhatsApp attachment.",
            )
        ],
        "heuristic",
        message,
        confidence=0.9,
        response_style="detailed",
        error=error,
    )


def _make_step(tool: str, args: dict[str, Any] | None = None, purpose: str = "") -> dict[str, Any]:
    return {
        "tool": tool,
        "args": args or {},
        "purpose": purpose or tool.replace("_", " "),
    }


def _plan_from_steps(
    steps: list[dict[str, Any]],
    source: str,
    message: str,
    confidence: float = 0.75,
    response_style: str = "short_spoken",
    error: str | None = None,
) -> dict[str, Any]:
    plan = {
        "mode": "tools" if steps else "chat",
        "requires_tools": bool(steps),
        "action": steps[0]["tool"] if steps else "chat",
        "steps": steps,
        "response_style": response_style,
        "confidence": confidence,
        "source": source,
        "input": message,
    }

    if error:
        plan["planner_error"] = error

    return _validate_plan(plan, source=source, message=message)


def _coerce_args(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    coerced = dict(args or {})

    if tool in {"open_app", "close_app"}:
        app = (
            coerced.get("app")
            or coerced.get("app_name")
            or coerced.get("application")
            or coerced.get("name")
        )
        coerced = {"app": _canonical_app_name(str(app or ""))}

    if tool in {"brave_search", "spotify_search", "web_search", "search_files"}:
        query = (
            coerced.get("query")
            or coerced.get("search_query")
            or coerced.get("q")
            or coerced.get("text")
        )
        coerced["query"] = str(query or "").strip()
        if tool == "search_files":
            scope = str(coerced.get("scope") or "").strip().lower()
            if scope in {"all", "finder", "mac", "computer", "everything"} and not coerced.get("root"):
                coerced["root"] = "home"
            if coerced.get("root"):
                coerced["root"] = str(coerced.get("root")).strip()
            if coerced.get("max_results") is not None:
                coerced["max_results"] = int(coerced.get("max_results") or 75)

    if tool == "send_message":
        receiver = (
            coerced.get("receiver")
            or coerced.get("recipient")
            or coerced.get("to")
            or coerced.get("contact")
        )
        body = (
            coerced.get("message_text")
            or coerced.get("message")
            or coerced.get("body")
            or coerced.get("text")
        )
        platform = _message_platform(str(coerced.get("platform") or coerced.get("service") or "messages"))
        dry_run = bool(coerced.get("dry_run", False))
        coerced = {
            "receiver": str(receiver or "").strip(),
            "message_text": str(body or "").strip(),
            "platform": platform,
            "auto_send": bool(coerced.get("auto_send", True)),
        }
        if dry_run:
            coerced["dry_run"] = True

    if tool == "send_resume_whatsapp":
        receiver = (
            coerced.get("receiver")
            or coerced.get("recipient")
            or coerced.get("to")
            or coerced.get("contact")
        )
        coerced["receiver"] = str(receiver or "").strip()
        for key in ("query", "file_path", "caption", "root"):
            if coerced.get(key) is not None:
                coerced[key] = str(coerced.get(key)).strip()
        for key in ("auto_send", "dry_run"):
            if key in coerced:
                coerced[key] = bool(coerced.get(key))

    if tool == "browser_agent":
        if not coerced.get("action"):
            if coerced.get("url"):
                coerced["action"] = "open_url"
            elif coerced.get("query"):
                coerced["action"] = "search"
            elif coerced.get("selector"):
                coerced["action"] = "click_selector"
            elif coerced.get("button_text"):
                coerced["action"] = "click_text"
            elif coerced.get("text"):
                coerced["action"] = "click_text"
            else:
                coerced["action"] = "status"
        coerced["action"] = str(coerced.get("action") or "status").strip() or "status"
        for key in ("url", "query", "text", "selector", "button_text", "key", "direction", "screenshot_path"):
            if coerced.get(key) is not None:
                coerced[key] = str(coerced.get(key)).strip()
        for key in ("amount",):
            if coerced.get(key) is not None:
                coerced[key] = int(coerced.get(key) or 0)
        for key in ("wait_seconds", "timeout_seconds"):
            if coerced.get(key) is not None:
                coerced[key] = float(coerced.get(key) or 0)

    if tool == "browser_task_agent":
        task = (
            coerced.get("task")
            or coerced.get("request")
            or coerced.get("instruction")
            or coerced.get("description")
            or coerced.get("query")
            or coerced.get("text")
        )
        coerced["task"] = str(task or "").strip()
        if coerced.get("start_url") is not None:
            coerced["start_url"] = str(coerced.get("start_url")).strip()
        if coerced.get("url") and not coerced.get("start_url"):
            coerced["start_url"] = str(coerced.get("url")).strip()
        if coerced.get("max_steps") is not None:
            coerced["max_steps"] = int(coerced.get("max_steps") or 18)
        if coerced.get("timeout_seconds") is not None:
            coerced["timeout_seconds"] = float(coerced.get("timeout_seconds") or 35)
        if coerced.get("user_login_wait_seconds") is not None:
            coerced["user_login_wait_seconds"] = float(coerced.get("user_login_wait_seconds") or 180)
        coerced["allow_purchase"] = False

    if tool == "read_file":
        path = coerced.get("path") or coerced.get("file_path") or coerced.get("file")
        coerced = {"path": str(path or "").strip()}

    if tool == "run_command":
        command = coerced.get("command") or coerced.get("cmd")
        coerced = {"command": str(command or "").strip()}

    if tool == "job_application_agent":
        query = (
            coerced.get("query")
            or coerced.get("request")
            or coerced.get("user_request")
            or coerced.get("text")
        )
        coerced["action"] = str(coerced.get("action") or "start").strip() or "start"
        coerced["query"] = str(query or "").strip()
        coerced["auto_apply"] = bool(coerced.get("auto_apply") or "apply" in coerced["query"].lower())
        email = coerced.get("email") or coerced.get("account_email")
        if email:
            coerced["email"] = str(email).strip()
        if coerced.get("source_scope"):
            coerced["source_scope"] = str(coerced["source_scope"]).strip()
        coerced["save_password_to_brave"] = bool(coerced.get("save_password_to_brave"))
        coerced["check_pages"] = bool(coerced.get("check_pages", True))
        coerced["brave_group"] = bool(coerced.get("brave_group", True))
        if "match_resume" in coerced:
            coerced["match_resume"] = bool(coerced.get("match_resume"))

    if tool == "job_automation_agent":
        query = coerced.get("query") or coerced.get("request") or coerced.get("text")
        coerced["action"] = str(coerced.get("action") or "status").strip() or "status"
        coerced["query"] = str(query or "").strip()
        if coerced.get("automation_id") is not None:
            coerced["automation_id"] = str(coerced.get("automation_id")).strip()
        if coerced.get("time") is not None:
            coerced["time"] = str(coerced.get("time")).strip()
        if coerced.get("source_scope") is not None:
            coerced["source_scope"] = str(coerced.get("source_scope")).strip()
        if coerced.get("notes") is not None:
            coerced["notes"] = str(coerced.get("notes")).strip()
        for key in ("max_applications",):
            if coerced.get(key) is not None:
                coerced[key] = int(coerced.get(key) or 10)
        for key in ("auto_apply_requested", "match_resume", "open_browser", "install_launch_agent"):
            if key in coerced:
                coerced[key] = bool(coerced.get(key))

    if tool == "shopping_agent":
        query = (
            coerced.get("query")
            or coerced.get("product")
            or coerced.get("search_query")
            or coerced.get("text")
        )
        coerced["action"] = str(coerced.get("action") or "research_add_to_cart").strip() or "research_add_to_cart"
        coerced["site"] = str(coerced.get("site") or "amazon").strip() or "amazon"
        coerced["query"] = str(query or "").strip()
        coerced["max_price"] = float(coerced.get("max_price") or coerced.get("budget") or 30)
        coerced["add_to_cart"] = bool(coerced.get("add_to_cart", True))
        if coerced.get("notes") is not None:
            coerced["notes"] = str(coerced.get("notes")).strip()
        if coerced.get("timeout_seconds") is not None:
            coerced["timeout_seconds"] = float(coerced.get("timeout_seconds") or 35)

    return coerced


def _validate_plan(raw_plan: dict[str, Any], source: str, message: str) -> dict[str, Any]:
    raw_steps = raw_plan.get("steps") or []

    if not raw_steps and raw_plan.get("tool"):
        raw_steps = [raw_plan]
    elif not raw_steps and raw_plan.get("action") not in (None, "chat"):
        raw_steps = [
            {
                "tool": raw_plan.get("action"),
                "args": {
                    key: value
                    for key, value in raw_plan.items()
                    if key
                    not in {
                        "action",
                        "mode",
                        "steps",
                        "requires_tools",
                        "response_style",
                        "confidence",
                        "source",
                    }
                },
                "purpose": raw_plan.get("reason") or raw_plan.get("purpose") or "",
            }
        ]

    steps: list[dict[str, Any]] = []

    for index, raw_step in enumerate(raw_steps[:MAX_PLAN_STEPS], start=1):
        raw_tool = str(raw_step.get("tool") or raw_step.get("action") or "").strip()
        tool = resolve_tool_name(raw_tool)

        if tool == "chat" or get_tool(tool) is None:
            continue

        step_args = raw_step.get("args") or {
            key: value
            for key, value in raw_step.items()
            if key
            not in {
                "id",
                "tool",
                "action",
                "purpose",
                "reason",
                "continue_on_error",
            }
        }
        if tool == "browser_agent":
            step_args = dict(step_args)
            step_args["action"] = _browser_alias_action(raw_tool, step_args)
        if tool == "browser_task_agent" and not any(
            step_args.get(key) for key in ("task", "request", "instruction", "description", "query", "text")
        ):
            step_args = {**step_args, "task": message}
        args = _coerce_args(tool, step_args)

        steps.append(
            {
                "id": raw_step.get("id") or f"step_{index}",
                "tool": tool,
                "args": args,
                "purpose": str(raw_step.get("purpose") or raw_step.get("reason") or ""),
                "continue_on_error": bool(raw_step.get("continue_on_error", False)),
            }
        )

    try:
        confidence = float(raw_plan.get("confidence", 0.7))
    except (TypeError, ValueError):
        confidence = 0.7

    plan = {
        "mode": "tools" if steps else "chat",
        "requires_tools": bool(steps),
        "action": steps[0]["tool"] if steps else "chat",
        "steps": steps,
        "response_style": raw_plan.get("response_style") or "short_spoken",
        "confidence": max(0.0, min(confidence, 1.0)),
        "source": source,
        "input": message,
    }

    if raw_plan.get("planner_error"):
        plan["planner_error"] = raw_plan["planner_error"]

    return plan


def normalize_plan(raw_plan: dict[str, Any], source: str, message: str) -> dict[str, Any]:
    return _validate_plan(raw_plan, source=source, message=message)


def _build_planner_messages(message: str, memory_context: str = "") -> list[dict[str, str]]:
    tools_json = json.dumps(planner_tool_specs(), ensure_ascii=True, indent=2)

    system_prompt = f"""
You are Dexter's intent planner.

Return only valid JSON. Do not include markdown, commentary, or hidden reasoning.
Use only tools from the catalog.
Create at most {MAX_PLAN_STEPS} ordered steps.

JSON shape:
{{
  "mode": "chat" or "tools",
  "response_style": "short_spoken" or "detailed",
  "confidence": 0.0,
  "steps": [
    {{
      "tool": "tool_name",
      "args": {{}},
      "purpose": "short reason"
    }}
  ]
}}

Planning rules:
- Use "chat" with an empty steps array for normal conversation that does not need tools.
- For "open brave and look up X", first open_app with app "Brave Browser", then brave_search with query X.
- For "search youtube for X", use brave_search with query "site:youtube.com X".
- For "play X on YouTube", use youtube_video with action "play" and query X.
- Use web_search when Dexter needs current web facts to answer or summarize, not just open a browser tab.
- Use close_app for phrases like "close Spotify" or "quit Brave".
- Use search_files with root "home" when the user asks to search "all my files", "my files", "home", or broad local files. Use file_controller for user Desktop/Downloads/Documents file actions.
- Use computer_settings for volume, mute, tabs, Activity Monitor, dark mode, and display actions.
- Use computer_control for explicit mouse, keyboard, typing, clipboard, and screenshots.
- Use browser_agent when the user asks Dexter to control the browser itself, inspect a page, click visible page text, type into a page, open a URL in the controlled browser, or check Dexter's browser status.
- Use browser_task_agent for multi-step browser workflows, arbitrary site tasks, and non-Amazon shopping/cart workflows that require navigating, clicking, selecting, typing, or reading pages.
- Use shopping_agent for Amazon shopping requests, product comparison, price-limited shopping, add-to-cart requests, and product research that may end with adding an item to cart. Never plan checkout or purchase.
- Use send_message for WhatsApp, Messages/iMessage/SMS, and email requests. Set platform "whatsapp" for WhatsApp. Do not claim a message was sent unless the tool result status says sent or attempted_send.
- Use audit_tools when the user asks to test, audit, or check whether all tools work.
- Use job_application_agent for job searches, internships, application workflows, signup/login workflows, and portal/source requests. Set action "start" for searches and "signup" for account creation/signup requests. Pass the original request as query. Set source_scope "all" when the user asks for all/more/different portals. Do not claim account creation is complete unless a tool result says it is complete.
- Use run_command only when the user explicitly asks to run a terminal command.
- Prefer simple one or two step plans unless the request clearly needs multiple steps.

Tool catalog:
{tools_json}
"""

    user_prompt = f"User request: {message}"

    if memory_context:
        user_prompt += f"\nRelevant memory:\n{memory_context[:1000]}"

    return [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_prompt},
    ]


def _heuristic_plan(message: str, error: str | None = None) -> dict[str, Any]:
    raw = _clean(message)
    msg = raw.lower()

    if msg in {"dexter", "hey dexter"}:
        return _plan_from_steps([], "heuristic", message, confidence=0.95, error=error)

    if msg in ("list apps", "show apps", "show applications", "list applications"):
        return _plan_from_steps(
            [_make_step("list_apps", {}, "List installed macOS applications.")],
            "heuristic",
            message,
            confidence=0.95,
            error=error,
        )

    if any(
        phrase in msg
        for phrase in (
            "test all tools",
            "audit all tools",
            "check all tools",
            "check if all tools work",
            "tool audit",
            "tools work",
        )
    ):
        return _plan_from_steps(
            [_make_step("audit_tools", {"include_side_effects": False}, "Audit registered Dexter tools.")],
            "heuristic",
            message,
            confidence=0.93,
            error=error,
        )

    if msg in {
        "browser agent status",
        "dexter browser status",
        "controlled browser status",
        "check browser agent",
    }:
        return _plan_from_steps(
            [_make_step("browser_agent", {"action": "status"}, "Check Dexter controlled browser status.")],
            "heuristic",
            message,
            confidence=0.94,
            error=error,
        )

    if any(
        phrase in msg
        for phrase in (
            "use already opened tab",
            "use the already opened tab",
            "use existing browser session",
            "use existing brave session",
            "reuse existing browser session",
            "reuse existing brave session",
            "reconnect existing browser session",
            "enable existing browser session",
        )
    ):
        return _plan_from_steps(
            [
                _make_step(
                    "browser_agent",
                    {"action": "attach_existing_session"},
                    "Attach to the existing browser session without quitting or relaunching it.",
                )
            ],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    if "relaunch existing browser session" in msg or "relaunch existing brave session" in msg:
        return _plan_from_steps(
            [
                _make_step(
                    "browser_agent",
                    {"action": "relaunch_existing_session"},
                    "Reopen the normal browser profile with CDP so Dexter can attach.",
                )
            ],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    if match := re.match(
        r"(?:open|go to|navigate to)\s+(.+?)\s+(?:in|with|using)\s+(?:the\s+)?(?:dexter\s+)?(?:controlled\s+)?browser$",
        raw,
        re.I,
    ):
        target_url = match.group(1).strip()
        return _plan_from_steps(
            [_make_step("browser_agent", {"action": "open_url", "url": target_url}, "Open URL in Dexter controlled browser.")],
            "heuristic",
            message,
            confidence=0.86,
            error=error,
        )

    if match := re.match(r"(?:click|press)\s+(.+?)\s+(?:in|on)\s+(?:the\s+)?browser$", raw, re.I):
        button_text = match.group(1).strip()
        return _plan_from_steps(
            [_make_step("browser_agent", {"action": "click_text", "button_text": button_text}, "Click text in Dexter controlled browser.")],
            "heuristic",
            message,
            confidence=0.82,
            error=error,
        )

    if match := re.match(r"type\s+(.+?)\s+(?:in|into)\s+(?:the\s+)?browser$", raw, re.I):
        text = match.group(1).strip()
        return _plan_from_steps(
            [_make_step("browser_agent", {"action": "type", "text": text}, "Type text in Dexter controlled browser.")],
            "heuristic",
            message,
            confidence=0.82,
            error=error,
        )

    if msg in {"inspect browser", "inspect page", "read browser page", "read current browser page"}:
        return _plan_from_steps(
            [_make_step("browser_agent", {"action": "inspect"}, "Inspect current Dexter browser page.")],
            "heuristic",
            message,
            confidence=0.86,
            error=error,
        )

    if msg.startswith(
        (
            "search all my files for ",
            "search my files for ",
            "find in all my files ",
            "find in my files ",
            "look through all my files for ",
            "look through my files for ",
        )
    ):
        query = _strip_prefix(
            raw,
            (
                "search all my files for ",
                "search my files for ",
                "find in all my files ",
                "find in my files ",
                "look through all my files for ",
                "look through my files for ",
            ),
        )
        return _plan_from_steps(
            [_make_step("search_files", {"query": query, "root": "home", "max_results": 75}, "Search user files.")],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    if resume_whatsapp_plan := _resume_whatsapp_plan_from_request(raw, message, error=error):
        return resume_whatsapp_plan

    if message_plan := _message_plan_from_request(raw, message, error=error):
        return message_plan

    if msg in {"job automation status", "internship automation status", "daily job automation status"}:
        return _plan_from_steps(
            [_make_step("job_automation_agent", {"action": "status"}, "Show job automation status.")],
            "heuristic",
            message,
            confidence=0.9,
            response_style="detailed",
            error=error,
        )

    if msg in {"run job automation", "run internship automation", "check internships now", "run morning internship scout"}:
        return _plan_from_steps(
            [
                _make_step(
                    "job_automation_agent",
                    {"action": "run", "automation_id": "morning_2027_cs_internships"},
                    "Run configured internship automation now.",
                )
            ],
            "heuristic",
            message,
            confidence=0.9,
            response_style="detailed",
            error=error,
        )

    if msg in {"disable job automation", "stop job automation", "disable internship automation", "stop internship automation"}:
        return _plan_from_steps(
            [
                _make_step(
                    "job_automation_agent",
                    {"action": "disable", "automation_id": "morning_2027_cs_internships"},
                    "Disable configured internship automation.",
                )
            ],
            "heuristic",
            message,
            confidence=0.9,
            response_style="detailed",
            error=error,
        )

    automation_requested = any(
        phrase in msg
        for phrase in (
            "every morning",
            "each morning",
            "daily",
            "automate",
            "automation",
            "recurring",
            "schedule",
        )
    )
    job_automation_requested = automation_requested and any(
        word in msg
        for word in (
            "intern",
            "internship",
            "internships",
            "job",
            "jobs",
            "application",
            "applications",
            "resume",
        )
    )
    if job_automation_requested:
        time_match = re.search(r"\b(?:at|around)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", raw, re.I)
        return _plan_from_steps(
            [
                _make_step(
                    "job_automation_agent",
                    {
                        "action": "setup",
                        "automation_id": "morning_2027_cs_internships",
                        "query": raw,
                        "time": time_match.group(1) if time_match else "09:00",
                        "source_scope": "all",
                        "max_applications": 10,
                        "auto_apply_requested": "apply" in msg or "applying" in msg,
                        "match_resume": "resume" in msg or "tailor" in msg or "fit" in msg,
                        "open_browser": True,
                        "install_launch_agent": True,
                        "notes": "Recurring internship scout. Final submission remains behind user review.",
                    },
                    "Set up recurring internship automation.",
                )
            ],
            "heuristic",
            message,
            confidence=0.9,
            response_style="detailed",
            error=error,
        )

    job_words = {
        "job",
        "jobs",
        "role",
        "roles",
        "position",
        "positions",
        "application",
        "applications",
        "intern",
        "interns",
        "internship",
        "internships",
        "new grad",
        "new-grad",
        "portal",
        "portals",
        "platform",
        "platforms",
        "source",
        "sources",
        "github",
        "intern-list",
        "intern list",
        "resume",
        "skill",
        "skills",
    }
    job_sites = {"linkedin", "dice", "glassdoor", "github", "intern-list", "intern list", "simplify", "greenhouse", "lever"}
    job_actions = {
        "apply",
        "applying",
        "find",
        "search",
        "latest",
        "look",
        "hunt",
        "sign up",
        "sign me up",
        "signup",
        "register",
        "create account",
        "gmail",
        "save password",
        "match",
        "matches",
    }

    if (
        any(word in msg for word in job_words)
        and (any(word in msg for word in job_actions) or any(site in msg for site in job_sites))
    ):
        email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", raw)
        signup_requested = any(
            phrase in msg
            for phrase in ("sign up", "sign me up", "signup", "register", "create account", "create accounts")
        )
        all_sources_requested = any(
            phrase in msg
            for phrase in (
                "all portals",
                "all platforms",
                "all sources",
                "more portals",
                "different sources",
                "not restricted",
                "not just",
            )
        )
        return _plan_from_steps(
            [
                _make_step(
                    "job_application_agent",
                    {
                        "action": "signup" if signup_requested else "start",
                        "query": raw,
                        "email": email_match.group(0) if email_match else "",
                        "source_scope": "all" if all_sources_requested else "",
                        "auto_apply": "apply" in msg or "applying" in msg,
                        "save_password_to_brave": "save password" in msg and "brave" in msg,
                        "match_resume": "resume" in msg or "skill" in msg or "skills" in msg,
                        "check_pages": True,
                        "brave_group": True,
                        "open_browser": True,
                    },
                    "Prepare a job application workflow.",
                )
            ],
            "heuristic",
            message,
            confidence=0.9,
            response_style="detailed",
            error=error,
        )

    if msg in {"job status", "latest job run", "job application status"}:
        return _plan_from_steps(
            [_make_step("job_application_agent", {"action": "status"}, "Show latest job application run.")],
            "heuristic",
            message,
            confidence=0.9,
            response_style="detailed",
            error=error,
        )

    if msg.startswith(("close ", "quit ", "kill app ")):
        app = _strip_prefix(raw, ("close ", "quit ", "kill app "))
        return _plan_from_steps(
            [_make_step("close_app", {"app": _canonical_app_name(app)}, f"Close {app}.")],
            "heuristic",
            message,
            confidence=0.95,
            error=error,
        )

    if msg.startswith(("search spotify for ", "spotify search ", "find song ", "search song ")):
        query = _strip_prefix(
            raw,
            ("search spotify for ", "spotify search ", "find song ", "search song "),
        )
        return _plan_from_steps(
            [_make_step("spotify_search", {"query": query}, "Search Spotify.")],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    if match := re.match(r"(?:what'?s|what is|show|get)\s+(?:the\s+)?weather(?:\s+in|\s+for)?\s+(.+)", raw, re.I):
        city = match.group(1).strip()
        return _plan_from_steps(
            [_make_step("weather_report", {"city": city}, f"Get weather for {city}.")],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    if msg.startswith(("weather in ", "weather for ")):
        city = _strip_prefix(raw, ("weather in ", "weather for "))
        return _plan_from_steps(
            [_make_step("weather_report", {"city": city}, f"Get weather for {city}.")],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    if match := re.match(r"(?:play|open)\s+(.+?)\s+(?:on\s+)?youtube$", raw, re.I):
        query = match.group(1).strip()
        return _plan_from_steps(
            [_make_step("youtube_video", {"action": "play", "query": query}, "Open YouTube video search.")],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    if "youtube trending" in msg or "trending on youtube" in msg:
        return _plan_from_steps(
            [_make_step("youtube_video", {"action": "trending", "region": "US"}, "Open YouTube trending.")],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    if match := re.search(r"summarize\s+(?:this\s+)?youtube\s+(?:video\s+)?(https?://\S+)", raw, re.I):
        url = match.group(1).strip()
        return _plan_from_steps(
            [_make_step("youtube_video", {"action": "summarize", "url": url}, "Summarize YouTube transcript.")],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    youtube_match = re.search(r"(?:search\s+)?youtube\s+(?:for\s+)?(.+)", raw, re.I)
    if youtube_match:
        query = youtube_match.group(1).strip()
        return _plan_from_steps(
            [
                _make_step(
                    "brave_search",
                    {"query": f"site:youtube.com {query}"},
                    "Open Brave with YouTube search results.",
                )
            ],
            "heuristic",
            message,
            confidence=0.85,
            error=error,
        )

    if "amazon" not in msg and _is_browser_workflow(raw):
        start_url = _infer_browser_start_url(raw)
        return _plan_from_steps(
            [
                _make_step(
                    "browser_task_agent",
                    {
                        "task": raw,
                        "start_url": start_url,
                        "max_steps": 18,
                        "allow_purchase": False,
                    },
                    "Run the requested multi-step browser workflow without checkout or purchase.",
                )
            ],
            "heuristic",
            message,
            confidence=0.84,
            response_style="detailed",
            error=error,
        )

    if msg.startswith(("go to ", "open website ", "open url ")):
        target = _strip_prefix(raw, ("go to ", "open website ", "open url "))
        url = _infer_browser_start_url(target) or target
        return _plan_from_steps(
            [_make_step("browser_agent", {"action": "open_url", "url": url}, "Open website.")],
            "heuristic",
            message,
            confidence=0.88,
            error=error,
        )

    if msg.startswith(("open brave and search ", "open brave and look up ")):
        query = _strip_prefix(raw, ("open brave and search ", "open brave and look up "))
        return _plan_from_steps(
            [
                _make_step("open_app", {"app": "Brave Browser"}, "Open Brave."),
                _make_step("brave_search", {"query": query}, "Search in Brave."),
            ],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    if msg.startswith(("search brave for ", "search a brave for ", "search for ", "look up ", "google ")):
        query = _strip_prefix(
            raw,
            ("search brave for ", "search a brave for ", "search for ", "look up ", "google "),
        )
        return _plan_from_steps(
            [_make_step("brave_search", {"query": query}, "Open browser search.")],
            "heuristic",
            message,
            confidence=0.8,
            error=error,
        )

    if msg in {"organize desktop", "clean desktop", "clean up desktop"}:
        return _plan_from_steps(
            [_make_step("desktop_control", {"action": "organize"}, "Organize desktop files.")],
            "heuristic",
            message,
            confidence=0.92,
            error=error,
        )

    if msg in {"list desktop", "show desktop files", "what is on my desktop"}:
        return _plan_from_steps(
            [_make_step("desktop_control", {"action": "list"}, "List desktop files.")],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    if msg in {"take screenshot", "screenshot", "capture screen", "screen shot"}:
        return _plan_from_steps(
            [_make_step("computer_control", {"action": "screenshot"}, "Capture a screenshot.")],
            "heuristic",
            message,
            confidence=0.95,
            error=error,
        )

    settings_actions = {
        "volume up": "volume_up",
        "turn volume up": "volume_up",
        "volume down": "volume_down",
        "turn volume down": "volume_down",
        "mute": "mute",
        "mute volume": "mute",
        "unmute": "unmute",
        "dark mode": "dark_mode",
        "toggle dark mode": "dark_mode",
        "open activity monitor": "activity_monitor",
        "activity monitor": "activity_monitor",
        "lock screen": "lock_screen",
        "sleep display": "sleep_display",
        "new tab": "new_tab",
        "close tab": "close_tab",
        "refresh page": "refresh_page",
        "copy": "copy",
        "paste": "paste",
        "save": "save",
    }
    if msg in settings_actions:
        action = settings_actions[msg]
        return _plan_from_steps(
            [_make_step("computer_settings", {"action": action}, f"Run {action}.")],
            "heuristic",
            message,
            confidence=0.92,
            error=error,
        )

    if match := re.match(r"(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})", raw, re.I):
        level = match.group(1)
        return _plan_from_steps(
            [_make_step("computer_settings", {"action": "volume_set", "value": level}, f"Set volume to {level}.")],
            "heuristic",
            message,
            confidence=0.93,
            error=error,
        )

    if match := re.match(r"(?:type|write)\s+(.+)", raw, re.I):
        text = match.group(1).strip()
        if not any(token in msg for token in (" file", " post", " email", "linkedin")):
            return _plan_from_steps(
                [_make_step("computer_control", {"action": "type", "text": text}, "Type text at cursor.")],
                "heuristic",
                message,
                confidence=0.82,
                error=error,
            )

    if message_plan := _message_plan_from_request(raw, message, error=error):
        return message_plan

    if match := re.match(r"(?:remind me to|set reminder to|reminder to)\s+(.+?)\s+(?:on|at)\s+(\d{4}-\d{2}-\d{2})\s+(?:at\s+)?(\d{1,2}:\d{2})", raw, re.I):
        body, date, time_value = match.groups()
        return _plan_from_steps(
            [_make_step("reminder", {"date": date, "time": time_value, "message": body.strip()}, "Set reminder.")],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    if match := re.match(r"find\s+flights?\s+from\s+(.+?)\s+to\s+(.+?)(?:\s+on\s+(.+))?$", raw, re.I):
        origin, destination, date = match.groups()
        return _plan_from_steps(
            [
                _make_step(
                    "flight_finder",
                    {"origin": origin.strip(), "destination": destination.strip(), "date": (date or "").strip()},
                    "Search flights.",
                )
            ],
            "heuristic",
            message,
            confidence=0.88,
            error=error,
        )

    if msg.startswith(("write file ", "create file ")):
        rest = _strip_prefix(raw, ("write file ", "create file "))
        name, _, content = rest.partition(" with ")
        return _plan_from_steps(
            [
                _make_step(
                    "file_controller",
                    {
                        "action": "write",
                        "path": "project",
                        "name": name.strip(),
                        "content": content.strip(),
                    },
                    "Write a safe local file.",
                )
            ],
            "heuristic",
            message,
            confidence=0.84,
            error=error,
        )

    if msg.startswith(("list files in ", "show files in ")):
        path = _strip_prefix(raw, ("list files in ", "show files in "))
        return _plan_from_steps(
            [_make_step("file_controller", {"action": "list", "path": path}, "List files.")],
            "heuristic",
            message,
            confidence=0.86,
            error=error,
        )

    if msg.startswith(("summarize file ", "analyze file ")):
        file_path = _strip_prefix(raw, ("summarize file ", "analyze file "))
        action = "summarize" if msg.startswith("summarize") else "analyze"
        return _plan_from_steps(
            [_make_step("file_processor", {"action": action, "file_path": file_path}, f"{action.title()} file.")],
            "heuristic",
            message,
            confidence=0.86,
            error=error,
        )

    if "amazon" in msg and any(
        phrase in msg
        for phrase in (
            "add",
            "cart",
            "buy",
            "browse",
            "shop",
            "shopping",
            "best",
            "reviews",
        )
    ):
        query = _infer_shopping_query(raw)
        max_price = _infer_max_price(raw) or 30.0
        return _plan_from_steps(
            [
                _make_step(
                    "shopping_agent",
                    {
                        "action": "research_add_to_cart" if "cart" in msg or "add" in msg else "research",
                        "site": "amazon",
                        "query": query,
                        "max_price": max_price,
                        "add_to_cart": "cart" in msg or "add" in msg,
                        "notes": raw,
                    },
                    "Research Amazon options and add one item to cart without checkout.",
                )
            ],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    if _is_browser_workflow(raw):
        start_url = _infer_browser_start_url(raw)
        return _plan_from_steps(
            [
                _make_step(
                    "browser_task_agent",
                    {
                        "task": raw,
                        "start_url": start_url,
                        "max_steps": 18,
                        "allow_purchase": False,
                    },
                    "Run the requested multi-step browser workflow without checkout or purchase.",
                )
            ],
            "heuristic",
            message,
            confidence=0.84,
            response_style="detailed",
            error=error,
        )

    if any(phrase in msg for phrase in ("latest", "news", "summarize", "research", "what happened")):
        query = _strip_prefix(
            raw,
            ("what is the latest ", "latest ", "news about ", "search web for ", "search internet for "),
        )

        if "linkedin post" in msg or "write a linkedin" in msg:
            steps = [
                _make_step("web_search", {"query": query}, "Find current web context."),
                _make_step(
                    "file_controller",
                    {
                        "action": "write",
                        "path": "desktop",
                        "name": "dexter_linkedin_draft.txt",
                    },
                    "Save draft context to Desktop.",
                ),
            ]
            return _plan_from_steps(
                steps,
                "heuristic",
                message,
                confidence=0.82,
                error=error,
            )

        return _plan_from_steps(
            [_make_step("web_search", {"query": query}, "Find current web context.")],
            "heuristic",
            message,
            confidence=0.8,
            error=error,
        )

    if msg.startswith(("open app ", "launch app ", "start app ")):
        app = _strip_prefix(raw, ("open app ", "launch app ", "start app "))
        return _plan_from_steps(
            [_make_step("open_app", {"app": _canonical_app_name(app)}, f"Open {app}.")],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    if msg.startswith(("open ", "launch ", "start ")):
        target = _strip_prefix(raw, ("open ", "launch ", "start "))
        file_like = (
            "/" in target
            or target.endswith(
                (".py", ".tsx", ".ts", ".js", ".json", ".md", ".txt", ".css", ".html")
            )
        )

        if file_like:
            return _plan_from_steps(
                [_make_step("read_file", {"path": target}, "Read requested file.")],
                "heuristic",
                message,
                confidence=0.85,
                error=error,
            )

        return _plan_from_steps(
            [_make_step("open_app", {"app": _canonical_app_name(target)}, f"Open {target}.")],
            "heuristic",
            message,
            confidence=0.85,
            error=error,
        )

    if msg.startswith(("read ", "open file ", "show file ")):
        path = _strip_prefix(raw, ("read ", "open file ", "show file "))
        return _plan_from_steps(
            [_make_step("read_file", {"path": path}, "Read requested file.")],
            "heuristic",
            message,
            confidence=0.85,
            error=error,
        )

    if msg.startswith(
        (
            "search all my files for ",
            "search my files for ",
            "find in all my files ",
            "find in my files ",
            "look through all my files for ",
            "look through my files for ",
        )
    ):
        query = _strip_prefix(
            raw,
            (
                "search all my files for ",
                "search my files for ",
                "find in all my files ",
                "find in my files ",
                "look through all my files for ",
                "look through my files for ",
            ),
        )
        return _plan_from_steps(
            [_make_step("search_files", {"query": query, "root": "home", "max_results": 75}, "Search user files.")],
            "heuristic",
            message,
            confidence=0.9,
            error=error,
        )

    if msg.startswith(("find file ", "search files for ", "search project for ", "locate file ")):
        query = _strip_prefix(
            raw,
            ("find file ", "search files for ", "search project for ", "locate file "),
        )
        return _plan_from_steps(
            [_make_step("search_files", {"query": query}, "Search project files.")],
            "heuristic",
            message,
            confidence=0.85,
            error=error,
        )

    if msg in SAFE_DIRECT_COMMANDS:
        return _plan_from_steps(
            [_make_step("run_command", {"command": msg}, "Run approved terminal command.")],
            "heuristic",
            message,
            confidence=0.95,
            error=error,
        )

    if msg.startswith(("run ", "execute ", "terminal ", "cmd ")):
        command = _strip_prefix(raw, ("run ", "execute ", "terminal ", "cmd "))
        return _plan_from_steps(
            [_make_step("run_command", {"command": command}, "Run requested command.")],
            "heuristic",
            message,
            confidence=0.8,
            error=error,
        )

    return _plan_from_steps([], "heuristic", message, confidence=0.65, error=error)


def determine_plan(message: str, memory_context: str = "") -> dict[str, Any]:
    heuristic = _heuristic_plan(message)
    planner_mode = os.getenv("DEXTER_PLANNER_MODE", "heuristic_first").lower()

    if _llm_planner_disabled():
        return heuristic

    if planner_mode in {"heuristic", "rules", "off"}:
        return heuristic

    if planner_mode != "llm_first":
        if heuristic.get("requires_tools") and heuristic.get("confidence", 0) >= 0.75:
            return heuristic

        if not heuristic.get("requires_tools"):
            return heuristic

    try:
        raw_plan = chat_json_completion(
            messages=_build_planner_messages(message, memory_context=memory_context),
            model=DEFAULT_PLANNER_MODEL,
            timeout=int(os.getenv("DEXTER_PLANNER_TIMEOUT", "20")),
            options={
                "temperature": 0,
                "num_ctx": 4096,
                "num_predict": int(os.getenv("DEXTER_PLANNER_NUM_PREDICT", "300")),
            },
        )
        return _validate_plan(raw_plan, source="llm", message=message)
    except Exception as e:
        return _heuristic_plan(message, error=str(e))


def determine_action(message: str) -> dict[str, Any]:
    plan = determine_plan(message)

    if not plan.get("steps"):
        return {"action": "chat"}

    first = plan["steps"][0]
    action = first["tool"]
    args = first.get("args", {})

    if action == "run_command":
        return {"action": "terminal", "command": args.get("command", "")}

    return {"action": action, **args}
