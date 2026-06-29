from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: str
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "enabled": self.enabled,
        }


def _object_schema(
    properties: dict[str, dict[str, Any]],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


TOOL_SPECS: dict[str, ToolSpec] = {
    "read_file": ToolSpec(
        name="read_file",
        description="Read a file inside Dexter's safe user roots, including the project and common user folders.",
        parameters=_object_schema(
            {
                "path": {
                    "type": "string",
                    "description": "Workspace-relative file path.",
                }
            },
            ["path"],
        ),
        handler="backend.tools.filesystem:read_file",
    ),
    "search_files": ToolSpec(
        name="search_files",
        description="Search file names and text inside Dexter's safe user roots. Use root home for broad user-file search.",
        parameters=_object_schema(
            {
                "query": {"type": "string", "description": "Search text."},
                "root": {
                    "type": "string",
                    "description": "Optional root: project, home, desktop, downloads, documents, career, personal, obsidian, or safe path.",
                    "default": ".",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum result count.",
                    "default": 75,
                },
            },
            ["query"],
        ),
        handler="backend.tools.filesystem:search_files",
    ),
    "run_command": ToolSpec(
        name="run_command",
        description="Run a terminal command through Dexter's permission policy.",
        parameters=_object_schema(
            {
                "command": {
                    "type": "string",
                    "description": "Exact shell command to run.",
                }
            },
            ["command"],
        ),
        handler="backend.tools.terminal:run_command",
    ),
    "open_app": ToolSpec(
        name="open_app",
        description="Open a macOS application.",
        parameters=_object_schema(
            {
                "app": {
                    "type": "string",
                    "description": "macOS app name, for example Brave Browser or Spotify.",
                }
            },
            ["app"],
        ),
        handler="backend.tools.macos:open_app",
    ),
    "close_app": ToolSpec(
        name="close_app",
        description="Quit a macOS application.",
        parameters=_object_schema(
            {
                "app": {
                    "type": "string",
                    "description": "macOS app name, for example Brave Browser or Spotify.",
                }
            },
            ["app"],
        ),
        handler="backend.tools.macos:close_app",
    ),
    "list_apps": ToolSpec(
        name="list_apps",
        description="List installed macOS applications.",
        parameters=_object_schema({}),
        handler="backend.tools.macos:list_apps",
    ),
    "spotify_search": ToolSpec(
        name="spotify_search",
        description="Open Spotify search for music, artists, albums, or podcasts.",
        parameters=_object_schema(
            {"query": {"type": "string", "description": "Spotify search query."}},
            ["query"],
        ),
        handler="backend.tools.macos:spotify_search",
    ),
    "brave_search": ToolSpec(
        name="brave_search",
        description="Open Brave Browser with a Google search results page.",
        parameters=_object_schema(
            {"query": {"type": "string", "description": "Browser search query."}},
            ["query"],
        ),
        handler="backend.tools.macos:brave_search",
    ),
    "web_search": ToolSpec(
        name="web_search",
        description="Search the web and return structured text results for Dexter to summarize.",
        parameters=_object_schema(
            {
                "query": {"type": "string", "description": "Web search query."},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum result count.",
                    "default": 5,
                },
            },
            ["query"],
        ),
        handler="backend.tools.web_search:web_search",
    ),
    "weather_report": ToolSpec(
        name="weather_report",
        description="Get or open weather information for a city.",
        parameters=_object_schema(
            {
                "city": {"type": "string", "description": "City or location."},
                "time": {"type": "string", "description": "Optional time, for example today or tomorrow."},
            },
            ["city"],
        ),
        handler="backend.tools.assistant_tools:weather_report",
    ),
    "youtube_video": ToolSpec(
        name="youtube_video",
        description="Search, play, summarize, or inspect YouTube videos.",
        parameters=_object_schema(
            {
                "action": {"type": "string", "description": "play, search, summarize, get_info, or trending."},
                "query": {"type": "string", "description": "YouTube search query."},
                "url": {"type": "string", "description": "YouTube URL for summarize/get_info."},
                "region": {"type": "string", "description": "Trending region code, for example US."},
                "save": {"type": "boolean", "description": "Save summary to Desktop."},
            },
            ["action"],
        ),
        handler="backend.tools.assistant_tools:youtube_video",
    ),
    "browser_control": ToolSpec(
        name="browser_control",
        description="Control Brave or another browser: go_to, search, new_tab, close_tab, refresh, back, forward, scroll, type, press.",
        parameters=_object_schema(
            {
                "action": {"type": "string", "description": "Browser action."},
                "url": {"type": "string", "description": "URL for go_to."},
                "query": {"type": "string", "description": "Search query."},
                "text": {"type": "string", "description": "Text to type."},
                "browser": {"type": "string", "description": "macOS browser app name."},
                "direction": {"type": "string", "description": "Scroll direction."},
                "amount": {"type": "integer", "description": "Amount for scroll."},
                "key": {"type": "string", "description": "Key to press."},
            },
            ["action"],
        ),
        handler="backend.tools.assistant_tools:browser_control",
    ),
    "browser_agent": ToolSpec(
        name="browser_agent",
        description="Control Dexter's Brave browser path: status, attach_existing_session, relaunch_existing_session, open_url, search, inspect, click_text, click_selector, type, press, scroll, screenshot, new_tab, close_tab, reload, back, forward, close.",
        parameters=_object_schema(
            {
                "action": {"type": "string", "description": "status, attach_existing_session, relaunch_existing_session, open_url, search, inspect, click_text, click_selector, type, press, scroll, screenshot, new_tab, close_tab, reload, back, forward, or close."},
                "url": {"type": "string", "description": "URL for open_url/go_to/navigate."},
                "query": {"type": "string", "description": "Search query."},
                "text": {"type": "string", "description": "Text to type or click."},
                "selector": {"type": "string", "description": "CSS selector for click/type."},
                "button_text": {"type": "string", "description": "Visible text to click."},
                "key": {"type": "string", "description": "Keyboard key for press."},
                "direction": {"type": "string", "description": "Scroll direction."},
                "amount": {"type": "integer", "description": "Scroll amount."},
                "wait_seconds": {"type": "number", "description": "Post-action wait."},
                "timeout_seconds": {"type": "number", "description": "Action timeout."},
                "screenshot_path": {"type": "string", "description": "Optional safe path for screenshot."},
            },
            ["action"],
        ),
        handler="backend.tools.browser_agent:browser_agent",
    ),
    "browser_task_agent": ToolSpec(
        name="browser_task_agent",
        description="Run a multi-step browser workflow in Dexter's controlled browser: navigate, search, click, type, select, scroll, inspect pages, and add to cart when requested. Never checks out or purchases.",
        parameters=_object_schema(
            {
                "task": {"type": "string", "description": "Natural-language browser task to complete."},
                "start_url": {"type": "string", "description": "Optional URL to open before starting."},
                "max_steps": {"type": "integer", "description": "Maximum browser action steps."},
                "timeout_seconds": {"type": "number", "description": "Browser action timeout."},
                "user_login_wait_seconds": {"type": "number", "description": "Seconds to wait while the user completes a manual login."},
                "allow_purchase": {"type": "boolean", "description": "Must remain false; checkout and purchase are not allowed."},
            },
            ["task"],
        ),
        handler="backend.tools.browser_task_agent:browser_task_agent",
    ),
    "file_controller": ToolSpec(
        name="file_controller",
        description="Manage files in safe user folders: list, read, write, create_file, create_folder, find, delete, move, copy, rename, disk_usage, largest, info.",
        parameters=_object_schema(
            {
                "action": {"type": "string", "description": "File action."},
                "path": {"type": "string", "description": "Safe path, shortcut, or root."},
                "name": {"type": "string", "description": "File or folder name."},
                "content": {"type": "string", "description": "Content for write/create_file."},
                "destination": {"type": "string", "description": "Move/copy destination."},
                "new_name": {"type": "string", "description": "Rename target name."},
                "extension": {"type": "string", "description": "Extension filter for find."},
                "max_results": {"type": "integer", "description": "Max results."},
                "append": {"type": "boolean", "description": "Append instead of overwrite."},
            },
            ["action"],
        ),
        handler="backend.tools.assistant_tools:file_controller",
    ),
    "computer_settings": ToolSpec(
        name="computer_settings",
        description="Control macOS settings and common shortcuts like volume, mute, dark mode, Activity Monitor, tabs, copy/paste, lock display.",
        parameters=_object_schema(
            {
                "action": {"type": "string", "description": "Settings action."},
                "value": {"type": "string", "description": "Optional numeric/string value."},
                "description": {"type": "string", "description": "Natural language fallback description."},
                "confirmed": {"type": "boolean", "description": "Required for dangerous actions."},
            },
            ["action"],
        ),
        handler="backend.tools.assistant_tools:computer_settings",
    ),
    "computer_control": ToolSpec(
        name="computer_control",
        description="Mouse, keyboard, clipboard, and screenshot control via pyautogui.",
        parameters=_object_schema(
            {
                "action": {"type": "string", "description": "type, smart_type, click, double_click, right_click, hotkey, press, scroll, screenshot, wait, copy, paste."},
                "text": {"type": "string", "description": "Text for type/paste."},
                "x": {"type": "integer", "description": "Screen x coordinate."},
                "y": {"type": "integer", "description": "Screen y coordinate."},
                "keys": {"type": "string", "description": "Hotkey like command+c."},
                "key": {"type": "string", "description": "Single key."},
                "direction": {"type": "string", "description": "Scroll direction."},
                "amount": {"type": "integer", "description": "Scroll amount."},
                "seconds": {"type": "number", "description": "Wait seconds."},
                "path": {"type": "string", "description": "Screenshot path."},
                "clear_first": {"type": "boolean", "description": "Clear field before smart typing."},
            },
            ["action"],
        ),
        handler="backend.tools.assistant_tools:computer_control",
    ),
    "desktop_control": ToolSpec(
        name="desktop_control",
        description="List, organize, clean, or set wallpaper for the Desktop.",
        parameters=_object_schema(
            {
                "action": {"type": "string", "description": "list, organize, clean, wallpaper, or task."},
                "path": {"type": "string", "description": "Wallpaper path or task path."},
                "task": {"type": "string", "description": "Desktop task description."},
            },
            ["action"],
        ),
        handler="backend.tools.assistant_tools:desktop_control",
    ),
    "screen_process": ToolSpec(
        name="screen_process",
        description="Capture the screen for later analysis or user inspection.",
        parameters=_object_schema(
            {
                "text": {"type": "string", "description": "Question or reason for capture."},
                "angle": {"type": "string", "description": "screen or camera."},
            }
        ),
        handler="backend.tools.assistant_tools:screen_process",
    ),
    "send_message": ToolSpec(
        name="send_message",
        description="Send or prepare a message via Messages, Brave WhatsApp Web, or email with honest sent/drafted status.",
        parameters=_object_schema(
            {
                "receiver": {"type": "string", "description": "Recipient name, phone, email, or handle."},
                "message_text": {"type": "string", "description": "Message body."},
                "platform": {"type": "string", "description": "messages, imessage, sms, mailto, email, WhatsApp, etc."},
                "auto_send": {"type": "boolean", "description": "Attempt to send when the platform supports local automation."},
                "dry_run": {"type": "boolean", "description": "Validate routing without opening or sending anything."},
            },
            ["receiver", "message_text"],
        ),
        handler="backend.tools.assistant_tools:send_message",
    ),
    "send_resume_whatsapp": ToolSpec(
        name="send_resume_whatsapp",
        description="Find a local resume file and send or draft it as a WhatsApp Web attachment through Dexter-controlled Brave.",
        parameters=_object_schema(
            {
                "receiver": {"type": "string", "description": "Recipient contact name or phone number."},
                "query": {"type": "string", "description": "Resume search query. Defaults to resume."},
                "file_path": {"type": "string", "description": "Optional explicit safe local resume path."},
                "caption": {"type": "string", "description": "Optional WhatsApp caption."},
                "root": {"type": "string", "description": "Safe local root to search, usually home."},
                "auto_send": {"type": "boolean", "description": "Attempt to click Send after attaching the file."},
                "dry_run": {"type": "boolean", "description": "Find the resume and report what would happen without opening WhatsApp."},
            },
            ["receiver"],
        ),
        handler="backend.tools.resume_share:send_resume_whatsapp",
    ),
    "reminder": ToolSpec(
        name="reminder",
        description="Schedule a macOS notification reminder.",
        parameters=_object_schema(
            {
                "date": {"type": "string", "description": "Date as YYYY-MM-DD."},
                "time": {"type": "string", "description": "Time as HH:MM."},
                "message": {"type": "string", "description": "Reminder text."},
            },
            ["date", "time", "message"],
        ),
        handler="backend.tools.assistant_tools:reminder",
    ),
    "flight_finder": ToolSpec(
        name="flight_finder",
        description="Search flight information for an origin, destination, and optional date.",
        parameters=_object_schema(
            {
                "origin": {"type": "string", "description": "Origin city or airport."},
                "destination": {"type": "string", "description": "Destination city or airport."},
                "date": {"type": "string", "description": "Optional travel date."},
            },
            ["origin", "destination"],
        ),
        handler="backend.tools.assistant_tools:flight_finder",
    ),
    "game_updater": ToolSpec(
        name="game_updater",
        description="Open Steam/Epic game update or download views.",
        parameters=_object_schema(
            {
                "action": {"type": "string", "description": "list, update, install, download_status, or schedule."},
                "platform": {"type": "string", "description": "steam, epic, or both."},
                "game_name": {"type": "string", "description": "Optional game name."},
                "shutdown_when_done": {"type": "boolean", "description": "Not performed without extra confirmation."},
            },
            ["action"],
        ),
        handler="backend.tools.assistant_tools:game_updater",
    ),
    "file_processor": ToolSpec(
        name="file_processor",
        description="Summarize, analyze, extract, or convert text from a safe local file.",
        parameters=_object_schema(
            {
                "action": {"type": "string", "description": "summarize, analyze, extract, or convert_to_text."},
                "file_path": {"type": "string", "description": "Safe file path."},
                "instruction": {"type": "string", "description": "Optional processing instruction."},
            },
            ["action", "file_path"],
        ),
        handler="backend.tools.assistant_tools:file_processor",
    ),
    "code_helper": ToolSpec(
        name="code_helper",
        description="Explain, review, write, or run code in safe paths.",
        parameters=_object_schema(
            {
                "action": {"type": "string", "description": "explain, review, write, edit, or run."},
                "description": {"type": "string", "description": "Code task description."},
                "language": {"type": "string", "description": "Programming language."},
                "file_path": {"type": "string", "description": "Existing code file."},
                "output_path": {"type": "string", "description": "Safe output path for write."},
            },
            ["action"],
        ),
        handler="backend.tools.assistant_tools:code_helper",
    ),
    "dev_agent": ToolSpec(
        name="dev_agent",
        description="Create a concise local development plan for a coding task.",
        parameters=_object_schema(
            {
                "description": {"type": "string", "description": "Development task."},
                "language": {"type": "string", "description": "Optional language/framework."},
                "path": {"type": "string", "description": "Safe project path."},
            },
            ["description"],
        ),
        handler="backend.tools.assistant_tools:dev_agent",
    ),
    "job_application_agent": ToolSpec(
        name="job_application_agent",
        description="Prepare and track browser-based job searches, internships, signup workflows, source expansion, and application runs across job boards, GitHub lists, intern lists, startup boards, and ATS/company boards with review checkpoints.",
        parameters=_object_schema(
            {
                "action": {"type": "string", "description": "start, signup, status, or latest."},
                "query": {"type": "string", "description": "Original natural-language job request."},
                "role": {"type": "string", "description": "Target role, for example Software Engineer."},
                "location": {"type": "string", "description": "Target location or Remote."},
                "sites": {"type": "string", "description": "Comma-separated source list, for example linkedin,github_search,simplify,greenhouse."},
                "source_scope": {"type": "string", "description": "Use all when the user asks for all/more/different portals."},
                "email": {"type": "string", "description": "Account email to use as a signup hint."},
                "browser": {"type": "string", "description": "macOS browser app name."},
                "max_applications": {"type": "integer", "description": "Maximum applications to prepare."},
                "auto_apply": {"type": "boolean", "description": "Whether the user requested applying, not just searching."},
                "open_browser": {"type": "boolean", "description": "Open search tabs in the browser."},
                "save_password_to_brave": {"type": "boolean", "description": "Whether the user wants Brave to save generated/user-entered passwords when prompted."},
                "match_resume": {"type": "boolean", "description": "Whether to use uploaded resume/docs for matching."},
                "check_pages": {"type": "boolean", "description": "Check URL status and skip/fallback 404 pages before opening."},
                "brave_group": {"type": "boolean", "description": "Open sources in a dedicated Brave window with a Dexter summary tab."},
                "notes": {"type": "string", "description": "Extra user criteria or constraints."},
            },
            ["action"],
        ),
        handler="backend.tools.job_agent:job_application_agent",
    ),
    "job_automation_agent": ToolSpec(
        name="job_automation_agent",
        description="Create, list, disable, or run recurring morning job/internship scouting automations with review checkpoints before final application submission.",
        parameters=_object_schema(
            {
                "action": {"type": "string", "description": "setup, run, status, list, or disable."},
                "query": {"type": "string", "description": "Job/internship scouting query."},
                "automation_id": {"type": "string", "description": "Stable automation identifier."},
                "time": {"type": "string", "description": "Daily time, for example 09:00."},
                "max_applications": {"type": "integer", "description": "Maximum applications/listings to prepare."},
                "auto_apply_requested": {"type": "boolean", "description": "Whether the requested workflow intends application prep. Final submit remains manual."},
                "match_resume": {"type": "boolean", "description": "Whether to use uploaded resume/docs once the resume tailoring pipeline is available."},
                "open_browser": {"type": "boolean", "description": "Open source tabs during scheduled runs."},
                "source_scope": {"type": "string", "description": "Use all for broad source coverage."},
                "install_launch_agent": {"type": "boolean", "description": "Install a macOS LaunchAgent for daily runs."},
                "notes": {"type": "string", "description": "Extra criteria or constraints."},
            },
            ["action"],
        ),
        handler="backend.tools.job_automation:job_automation_agent",
    ),
    "shopping_agent": ToolSpec(
        name="shopping_agent",
        description="Research Amazon shopping results, compare price/rating/review counts, and optionally add one item to cart without checkout or purchase.",
        parameters=_object_schema(
            {
                "action": {"type": "string", "description": "research_add_to_cart, research, or add_to_cart."},
                "site": {"type": "string", "description": "Shopping site. Currently supports amazon."},
                "query": {"type": "string", "description": "Product search query."},
                "max_price": {"type": "number", "description": "Maximum item price in USD."},
                "add_to_cart": {"type": "boolean", "description": "Whether to add the selected product to cart. Never checks out."},
                "notes": {"type": "string", "description": "Extra shopping criteria or constraints."},
                "timeout_seconds": {"type": "number", "description": "Browser action timeout."},
            },
            ["action", "query"],
        ),
        handler="backend.tools.shopping_agent:shopping_agent",
    ),
    "audit_tools": ToolSpec(
        name="audit_tools",
        description="Audit Dexter tool registration and run safe smoke tests without opening apps or sending real messages.",
        parameters=_object_schema(
            {
                "include_side_effects": {
                    "type": "boolean",
                    "description": "Run side-effect tools too. Defaults to false and should stay false for normal audits.",
                }
            }
        ),
        handler="backend.tools.tool_audit:audit_tools",
    ),
}

TOOL_ALIASES = {
    "file_read": "read_file",
    "project_search": "search_files",
    "terminal": "run_command",
    "terminal_command": "run_command",
    "macos_app_control": "open_app",
    "weather": "weather_report",
    "youtube": "youtube_video",
    "desktop": "desktop_control",
    "settings": "computer_settings",
    "screen": "screen_process",
    "controlled_browser": "browser_agent",
    "browser_agent_status": "browser_agent",
    "browser_navigate": "browser_agent",
    "browser_open": "browser_agent",
    "browser_goto": "browser_agent",
    "browser_go_to": "browser_agent",
    "browser_click": "browser_agent",
    "browser_type": "browser_agent",
    "browser_fill": "browser_agent",
    "browser_press": "browser_agent",
    "browser_scroll": "browser_agent",
    "browser_read": "browser_agent",
    "browser_inspect": "browser_agent",
    "browser_task": "browser_task_agent",
    "web_task": "browser_task_agent",
    "browser_workflow": "browser_task_agent",
    "message": "send_message",
    "resume_whatsapp": "send_resume_whatsapp",
    "whatsapp_resume": "send_resume_whatsapp",
    "agent_task": "dev_agent",
    "jobs": "job_application_agent",
    "job_agent": "job_application_agent",
    "job_applications": "job_application_agent",
    "job_automation": "job_automation_agent",
    "job_scheduler": "job_automation_agent",
    "internship_automation": "job_automation_agent",
    "finder_search": "search_files",
    "audit": "audit_tools",
    "tool_audit": "audit_tools",
}


def resolve_tool_name(name: str) -> str:
    clean = (name or "").strip()
    return TOOL_ALIASES.get(clean, clean)


def get_tool(name: str) -> ToolSpec | None:
    return TOOL_SPECS.get(resolve_tool_name(name))


def list_tools() -> dict[str, dict[str, Any]]:
    return {name: spec.to_dict() for name, spec in TOOL_SPECS.items()}


def planner_tool_specs() -> list[dict[str, Any]]:
    return [spec.to_dict() for spec in TOOL_SPECS.values() if spec.enabled]


def _load_handler(handler_path: str) -> Callable[..., dict[str, Any]]:
    module_name, function_name = handler_path.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, function_name)


def execute_registered_tool(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = get_tool(name)

    if spec is None:
        return {"ok": False, "error": f"Unknown tool: {name}"}

    if not spec.enabled:
        return {"ok": False, "error": f"Tool disabled: {spec.name}"}

    tool_args = args or {}
    allowed_args = set(spec.parameters.get("properties", {}).keys())
    filtered_args = {
        key: value
        for key, value in tool_args.items()
        if key in allowed_args and value is not None
    }

    missing = [
        key
        for key in spec.parameters.get("required", [])
        if key not in filtered_args or filtered_args[key] == ""
    ]

    if missing:
        return {
            "ok": False,
            "tool": spec.name,
            "error": f"Missing required argument(s): {', '.join(missing)}",
        }

    try:
        handler = _load_handler(spec.handler)
        return handler(**filtered_args)
    except Exception as e:
        return {"ok": False, "tool": spec.name, "error": str(e)}
