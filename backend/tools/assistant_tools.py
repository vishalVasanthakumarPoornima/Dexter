from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from backend.models.ollama_client import chat_with_ollama
from backend.tools import web_search as web_search_tool
from backend.tools.safe_paths import PROJECT_ROOT, USER_HOME, resolve_safe_path, safe_roots
from backend.utils.logger import log_action


HOME = USER_HOME
DEFAULT_SAFE_ROOTS = [
    HOME / "Desktop",
    HOME / "Downloads",
    HOME / "Documents",
    HOME / "Pictures",
    HOME / "Movies",
    HOME / "Music",
    PROJECT_ROOT,
]


def _ok(tool: str, **payload: Any) -> dict[str, Any]:
    result = {"ok": True, "tool": tool, **payload}
    log_action(tool, result)
    return result


def _fail(tool: str, error: str, **payload: Any) -> dict[str, Any]:
    result = {"ok": False, "tool": tool, "error": error, **payload}
    log_action(f"{tool}_error", result)
    return result


def _safe_roots() -> list[Path]:
    return safe_roots()


def _resolve_path(path: str = "", name: str = "") -> Path:
    return resolve_safe_path(path or "project", name=name)


def _open_url(url: str, app: str | None = None) -> None:
    command = ["open"]

    if app:
        command.extend(["-a", app])

    command.append(url)
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=12)


def _pyautogui():
    try:
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        return pyautogui
    except Exception as e:
        raise RuntimeError("pyautogui is not installed or not available") from e


def _pyperclip():
    try:
        import pyperclip

        return pyperclip
    except Exception:
        return None


def _applescript_string(value: str) -> str:
    return json.dumps(value)


def _run_osascript(script: str, timeout: int = 12) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["osascript", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _clean_phone(value: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", value)
    if cleaned.count("+") > 1:
        cleaned = cleaned.replace("+", "")
    if "+" in cleaned and not cleaned.startswith("+"):
        cleaned = cleaned.replace("+", "")
    return cleaned


def _looks_like_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    return len(digits) >= 7


def _contact_aliases_path() -> Path:
    configured = os.getenv("DEXTER_CONTACT_ALIASES_PATH", "data/contact_aliases.json").strip()
    if Path(configured).is_absolute():
        return resolve_safe_path(configured)
    return resolve_safe_path(str(PROJECT_ROOT / configured))


def _normalize_contact_alias_key(value: str) -> str:
    clean = re.sub(r"^(?:my|the)\s+", "", value.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]+", "", clean.lower())


def _read_contact_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}

    raw_env = os.getenv("DEXTER_CONTACT_ALIASES_JSON", "").strip()
    if raw_env:
        try:
            data = json.loads(raw_env)
            if isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, str):
                        aliases[_normalize_contact_alias_key(str(key))] = value
                    elif isinstance(value, dict) and isinstance(value.get("phone"), str):
                        aliases[_normalize_contact_alias_key(str(key))] = value["phone"]
        except json.JSONDecodeError:
            pass

    try:
        path = _contact_aliases_path()
    except Exception:
        return aliases

    if not path.exists():
        return aliases

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return aliases

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                aliases[_normalize_contact_alias_key(str(key))] = value
            elif isinstance(value, dict) and isinstance(value.get("phone"), str):
                aliases[_normalize_contact_alias_key(str(key))] = value["phone"]

    return aliases


def _lookup_contact_alias_phone(name: str) -> str:
    aliases = _read_contact_aliases()
    if not aliases:
        return ""

    keys = [
        _normalize_contact_alias_key(name),
        _normalize_contact_alias_key(re.sub(r"^(?:my|the)\s+", "", name, flags=re.I)),
    ]
    for key in keys:
        phone = aliases.get(key, "")
        if _looks_like_phone(phone):
            return _clean_phone(phone)

    return ""


def _phone_for_whatsapp(value: str) -> str:
    cleaned = _clean_phone(value)
    digits = re.sub(r"\D", "", cleaned)

    if cleaned.startswith("+"):
        return digits

    default_country = re.sub(r"\D", "", os.getenv("DEXTER_DEFAULT_COUNTRY_CODE", "1")) or "1"
    if len(digits) == 10:
        return f"{default_country}{digits}"

    return digits


def _lookup_contact_phone(name: str) -> tuple[str, str]:
    clean_name = name.strip()
    if not clean_name:
        return "", "No contact name provided."

    if _looks_like_phone(clean_name):
        return _clean_phone(clean_name), ""

    if alias_phone := _lookup_contact_alias_phone(clean_name):
        return alias_phone, ""

    candidate_names = [clean_name]
    normalized_name = re.sub(r"^(?:my|the)\s+", "", clean_name, flags=re.I).strip()
    if normalized_name and normalized_name.lower() != clean_name.lower():
        candidate_names.append(normalized_name)

    script = f"""
tell application "Contacts"
  set searchNames to {{{", ".join(_applescript_string(candidate) for candidate in candidate_names)}}}
  repeat with searchName in searchNames
    set matches to every person whose name contains searchName
    if (count of matches) is greater than 0 then
      repeat with matchedPerson in matches
        if (count of phones of matchedPerson) is greater than 0 then
          return value of item 1 of phones of matchedPerson
        end if
      end repeat
    end if
  end repeat
end tell
"""

    try:
        completed = _run_osascript(script, timeout=10)
        phone = _clean_phone(completed.stdout.strip())
        if phone:
            return phone, ""
        return "", f"No phone number found for {clean_name} in macOS Contacts."
    except subprocess.CalledProcessError as e:
        details = (e.stderr or e.stdout or str(e)).strip()
        hint = (
            "Add a private alias in data/contact_aliases.json, use the phone number directly, "
            "or grant Contacts/Automation access to the app that launched Dexter."
        )
        return "", f"Could not read macOS Contacts for {clean_name}: {details}. {hint}"
    except Exception as e:
        hint = (
            "Add a private alias in data/contact_aliases.json, use the phone number directly, "
            "or grant Contacts/Automation access to the app that launched Dexter."
        )
        return "", f"Could not read macOS Contacts for {clean_name}: {e}. {hint}"


def _send_imessage(receiver: str, message_text: str) -> dict[str, Any]:
    handle, error = _lookup_contact_phone(receiver)
    if not handle:
        handle = receiver.strip() if "@" in receiver else ""

    if not handle:
        return _fail("send_message", error or "No phone/email handle found for Messages.", receiver=receiver)

    script = f"""
tell application "Messages"
  set targetService to 1st service whose service type = iMessage
  set targetBuddy to buddy {_applescript_string(handle)} of targetService
  send {_applescript_string(message_text)} to targetBuddy
end tell
"""

    try:
        _run_osascript(script, timeout=15)
        return _ok(
            "send_message",
            platform="messages",
            receiver=receiver,
            status="sent",
            sent=True,
            output=f"Sent message to {receiver} through Messages.",
        )
    except Exception as e:
        return _fail(
            "send_message",
            f"Messages could not send to {receiver}: {e}",
            platform="messages",
            receiver=receiver,
            sent=False,
        )


def _open_whatsapp_message(receiver: str, message_text: str, auto_send: bool) -> dict[str, Any]:
    whatsapp_phone = _phone_for_whatsapp(receiver) if _looks_like_phone(receiver) else ""
    try:
        from backend.tools.browser_agent import send_whatsapp_via_brave

        result = send_whatsapp_via_brave(
            phone=whatsapp_phone,
            message_text=message_text,
            receiver=receiver,
            auto_send=auto_send,
        )
        result["tool"] = "send_message"
        return result
    except Exception as e:
        return _fail(
            "send_message",
            str(e),
            platform="whatsapp",
            receiver=receiver,
            phone=whatsapp_phone,
            sent=False,
        )


def browser_control(
    action: str,
    url: str = "",
    query: str = "",
    text: str = "",
    browser: str = "Brave Browser",
    direction: str = "down",
    amount: int = 5,
    key: str = "enter",
) -> dict[str, Any]:
    action = action.strip().lower().replace("-", "_")

    if browser.strip().lower() in {"brave", "brave browser", "dexter", "controlled"}:
        try:
            from backend.tools.browser_agent import browser_agent

            action_map = {
                "go_to": "open_url",
                "search": "search",
                "new_tab": "new_tab",
                "close": "close_tab",
                "close_tab": "close_tab",
                "refresh": "reload",
                "reload": "reload",
                "back": "back",
                "forward": "forward",
                "scroll": "scroll",
                "type": "type",
                "press": "press",
                "screenshot": "screenshot",
                "inspect": "inspect",
                "click_text": "click_text",
                "click_selector": "click_selector",
            }
            if action in action_map:
                result = browser_agent(
                    action=action_map[action],
                    url=url,
                    query=query,
                    text=text,
                    button_text=text,
                    direction=direction,
                    amount=amount,
                    key=key,
                )
                result["tool"] = "browser_control"
                return result
        except Exception:
            pass

    try:
        if action == "go_to":
            destination = url.strip()
            if destination and "://" not in destination:
                destination = "https://" + destination
            _open_url(destination or "about:blank", app=browser)
            return _ok("browser_control", action=action, output=f"Opened {destination}")

        if action == "search":
            clean = query or text
            encoded = urllib.parse.quote_plus(clean.strip())
            destination = f"https://www.google.com/search?q={encoded}"
            _open_url(destination, app=browser)
            return _ok("browser_control", action=action, output=f"Searched for {clean}")

        pg = _pyautogui()
        modifier = "command"

        if action == "new_tab":
            pg.hotkey(modifier, "t")
        elif action in {"close", "close_tab"}:
            pg.hotkey(modifier, "w")
        elif action in {"refresh", "reload"}:
            pg.hotkey(modifier, "r")
        elif action == "back":
            pg.hotkey(modifier, "left")
        elif action == "forward":
            pg.hotkey(modifier, "right")
        elif action == "scroll":
            pg.scroll(abs(int(amount)) if direction == "up" else -abs(int(amount)))
        elif action == "type":
            clip = _pyperclip()
            if clip:
                clip.copy(text)
                pg.hotkey(modifier, "v")
            else:
                pg.write(text, interval=0.02)
        elif action == "press":
            pg.press(key)
        else:
            return _fail("browser_control", f"Unknown browser action: {action}", action=action)

        return _ok("browser_control", action=action, output=f"Browser action completed: {action}")
    except Exception as e:
        return _fail("browser_control", str(e), action=action)


def weather_report(city: str, time: str = "today") -> dict[str, Any]:
    clean = city.strip()
    when = (time or "today").strip()

    if not clean:
        return _fail("weather_report", "No city provided.")

    try:
        response = requests.get(f"https://wttr.in/{urllib.parse.quote(clean)}", params={"format": "3"}, timeout=8)
        if response.ok and response.text.strip():
            return _ok("weather_report", city=clean, output=response.text.strip())
    except Exception:
        pass

    query = f"weather in {clean} {when}"
    result = web_search_tool.web_search(query=query, max_results=3)
    if result.get("ok"):
        return _ok(
            "weather_report",
            city=clean,
            output=f"Found weather search results for {clean}.",
            results=result.get("results", []),
        )

    return _fail("weather_report", result.get("error", "Weather lookup failed."), city=clean)


def reminder(date: str, time: str, message: str) -> dict[str, Any]:
    try:
        target_dt = datetime.strptime(f"{date.strip()} {time.strip()}", "%Y-%m-%d %H:%M")
    except ValueError:
        return _fail("reminder", "Use date YYYY-MM-DD and time HH:MM.")

    if target_dt <= datetime.now():
        return _fail("reminder", "Reminder time is in the past.")

    safe_message = re.sub(r"[\r\n\"']", " ", message.strip())[:200] or "Reminder"
    label = f"com.dexter.reminder.{target_dt.strftime('%Y%m%d%H%M%S')}"
    script_dir = HOME / ".dexter" / "reminders"
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / f"{label}.py"
    script_path.write_text(
        "import subprocess\n"
        f"message = {json.dumps(safe_message)}\n"
        "script = 'display notification ' + __import__('json').dumps(message) + ' with title \"Dexter Reminder\"'\n"
        "subprocess.run(['osascript', '-e', script], check=False)\n"
        "try:\n"
        "    __import__('pathlib').Path(__file__).unlink(missing_ok=True)\n"
        "except Exception:\n"
        "    pass\n",
        encoding="utf-8",
    )
    script_path.chmod(0o600)

    plist_dir = HOME / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / f"{label}.plist"
    plist_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>{script_path}</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Year</key><integer>{target_dt.year}</integer>
    <key>Month</key><integer>{target_dt.month}</integer>
    <key>Day</key><integer>{target_dt.day}</integer>
    <key>Hour</key><integer>{target_dt.hour}</integer>
    <key>Minute</key><integer>{target_dt.minute}</integer>
  </dict>
  <key>StandardOutPath</key><string>/dev/null</string>
  <key>StandardErrorPath</key><string>/dev/null</string>
</dict>
</plist>
""",
        encoding="utf-8",
    )

    completed = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True, timeout=10)
    if completed.returncode != 0:
        return _fail("reminder", completed.stderr.strip() or "launchctl could not load reminder.")

    friendly = target_dt.strftime("%B %d at %I:%M %p")
    return _ok("reminder", output=f"Reminder set for {friendly}.", date=date, time=time, message=safe_message)


def youtube_video(action: str = "play", query: str = "", url: str = "", region: str = "US", save: bool = False) -> dict[str, Any]:
    action = action.strip().lower()

    def _video_id(raw_url: str) -> str | None:
        match = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", raw_url)
        return match.group(1) if match else None

    try:
        if action in {"play", "search"}:
            clean = query.strip()
            if not clean:
                return _fail("youtube_video", "No YouTube query provided.")
            destination = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(clean)
            _open_url(destination, app="Brave Browser")
            return _ok("youtube_video", action=action, output=f"Opened YouTube search for {clean}.", url=destination)

        if action == "trending":
            destination = f"https://www.youtube.com/feed/trending?gl={urllib.parse.quote(region.upper())}"
            _open_url(destination, app="Brave Browser")
            return _ok("youtube_video", action=action, output=f"Opened YouTube trending for {region.upper()}.", url=destination)

        if action in {"summarize", "get_info"}:
            video_url = url.strip()
            if not video_url:
                return _fail("youtube_video", "A YouTube URL is required for this action.")

            video_id = _video_id(video_url)
            if not video_id:
                return _fail("youtube_video", "Could not extract a YouTube video ID.")

            if action == "get_info":
                return _ok("youtube_video", action=action, output=f"YouTube video ID: {video_id}", video_id=video_id)

            try:
                from youtube_transcript_api import YouTubeTranscriptApi
            except Exception:
                return _fail("youtube_video", "youtube-transcript-api is not installed.")

            transcript_items = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
            transcript = " ".join(item.get("text", "") for item in transcript_items)
            summary = chat_with_ollama(
                "Summarize this YouTube transcript in 5 concise bullets:\n\n" + transcript[:12000]
            )

            saved_path = ""
            if save:
                target = _resolve_path("desktop", f"youtube_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
                target.write_text(summary, encoding="utf-8")
                saved_path = str(target)

            return _ok("youtube_video", action=action, output=summary, saved_path=saved_path)

        return _fail("youtube_video", f"Unknown YouTube action: {action}.")
    except Exception as e:
        return _fail("youtube_video", str(e), action=action)


def file_controller(
    action: str,
    path: str = "project",
    name: str = "",
    content: str = "",
    destination: str = "",
    new_name: str = "",
    extension: str = "",
    max_results: int = 20,
    append: bool = False,
) -> dict[str, Any]:
    action = action.strip().lower()

    try:
        target = _resolve_path(path, name)

        if action == "list":
            if not target.is_dir():
                return _fail("file_controller", "Path is not a directory.", path=str(target))
            items = [
                {"name": item.name, "type": "directory" if item.is_dir() else "file"}
                for item in sorted(target.iterdir())
                if not item.name.startswith(".")
            ]
            return _ok("file_controller", action=action, path=str(target), items=items[:200])

        if action in {"read", "info"}:
            if not target.exists():
                return _fail("file_controller", "Path not found.", path=str(target))
            if action == "info":
                stat = target.stat()
                return _ok(
                    "file_controller",
                    action=action,
                    path=str(target),
                    output=f"{target.name}: {stat.st_size} bytes, modified {datetime.fromtimestamp(stat.st_mtime)}",
                )
            if not target.is_file():
                return _fail("file_controller", "Path is not a file.", path=str(target))
            text = target.read_text(encoding="utf-8", errors="replace")
            return _ok("file_controller", action=action, path=str(target), content=text[:12000])

        if action in {"write", "create_file"}:
            target.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with target.open(mode, encoding="utf-8") as handle:
                handle.write(content)
            return _ok("file_controller", action=action, path=str(target), output=f"Wrote {target.name}.")

        if action == "create_folder":
            target.mkdir(parents=True, exist_ok=True)
            return _ok("file_controller", action=action, path=str(target), output=f"Created folder {target.name}.")

        if action == "find":
            root = target if target.is_dir() else target.parent
            matches = []
            for item in root.rglob("*"):
                if len(matches) >= int(max_results):
                    break
                if not item.is_file():
                    continue
                if extension and item.suffix.lower() != extension.lower():
                    continue
                if name and name.lower() not in item.name.lower():
                    continue
                matches.append(str(item))
            return _ok("file_controller", action=action, matches=matches)

        if action == "delete":
            try:
                import send2trash
            except Exception:
                return _fail("file_controller", "send2trash is required for safe delete.")
            send2trash.send2trash(str(target))
            return _ok("file_controller", action=action, output=f"Moved {target.name} to Trash.")

        if action in {"move", "copy"}:
            if not destination:
                return _fail("file_controller", "Destination is required.")
            dest = _resolve_path(destination)
            if dest.is_dir():
                dest = dest / target.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if action == "move":
                shutil.move(str(target), str(dest))
            elif target.is_dir():
                shutil.copytree(str(target), str(dest))
            else:
                shutil.copy2(str(target), str(dest))
            return _ok("file_controller", action=action, output=f"{action.title()}d {target.name}.", destination=str(dest))

        if action == "rename":
            if not new_name:
                return _fail("file_controller", "new_name is required.")
            new_path = target.parent / new_name
            target.rename(new_path)
            return _ok("file_controller", action=action, output=f"Renamed {target.name} to {new_name}.")

        if action in {"disk_usage", "largest"}:
            root = target if target.is_dir() else target.parent
            if action == "disk_usage":
                usage = shutil.disk_usage(root)
                return _ok("file_controller", action=action, total=usage.total, used=usage.used, free=usage.free)
            files = sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.stat().st_size, reverse=True)
            largest = [{"path": str(p), "size": p.stat().st_size} for p in files[: int(max_results)]]
            return _ok("file_controller", action=action, files=largest)

        return _fail("file_controller", f"Unknown file action: {action}.")
    except Exception as e:
        return _fail("file_controller", str(e), action=action)


def desktop_control(action: str = "list", path: str = "", task: str = "") -> dict[str, Any]:
    action = action.strip().lower()
    desktop = _resolve_path("desktop")

    try:
        if action == "list":
            return file_controller(action="list", path=str(desktop))

        if action in {"organize", "clean"}:
            categories = {
                "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"},
                "Documents": {".pdf", ".doc", ".docx", ".txt", ".md", ".csv", ".xls", ".xlsx", ".ppt", ".pptx"},
                "Videos": {".mp4", ".mov", ".mkv", ".avi", ".webm"},
                "Audio": {".mp3", ".wav", ".m4a", ".flac"},
                "Archives": {".zip", ".tar", ".gz", ".7z", ".rar"},
                "Code": {".py", ".js", ".ts", ".tsx", ".html", ".css", ".json", ".sh"},
            }
            moved = []
            for item in desktop.iterdir():
                if item.is_dir() or item.name.startswith("."):
                    continue
                folder = "Other"
                for category, exts in categories.items():
                    if item.suffix.lower() in exts:
                        folder = category
                        break
                dest_dir = desktop / folder
                dest_dir.mkdir(exist_ok=True)
                dest = dest_dir / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
                    moved.append(f"{item.name} -> {folder}")
            return _ok("desktop_control", action=action, output=f"Organized {len(moved)} desktop file(s).", moved=moved)

        if action == "wallpaper":
            image = _resolve_path(path)
            script = f'tell application "System Events" to tell every desktop to set picture to POSIX file {json.dumps(str(image))}'
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True, timeout=10)
            return _ok("desktop_control", action=action, output=f"Wallpaper set to {image.name}.")

        if action == "task":
            return _ok("desktop_control", action=action, output="Desktop task noted.", task=task)

        return _fail("desktop_control", f"Unknown desktop action: {action}.")
    except Exception as e:
        return _fail("desktop_control", str(e), action=action)


def computer_settings(action: str, value: str = "", description: str = "", confirmed: bool = False) -> dict[str, Any]:
    action = (action or description).strip().lower().replace(" ", "_").replace("-", "_")
    dangerous = {"restart", "shutdown", "toggle_wifi"}

    if action in dangerous and not confirmed:
        return _fail("computer_settings", f"{action} requires confirmed=true.", action=action)

    try:
        pg = None

        if action == "volume_set":
            level = max(0, min(100, int(value)))
            subprocess.run(["osascript", "-e", f"set volume output volume {level}"], check=True, capture_output=True, text=True, timeout=5)
        elif action == "volume_up":
            subprocess.run(["osascript", "-e", "set volume output volume (output volume of (get volume settings) + 10)"], check=True, capture_output=True, text=True, timeout=5)
        elif action == "volume_down":
            subprocess.run(["osascript", "-e", "set volume output volume (output volume of (get volume settings) - 10)"], check=True, capture_output=True, text=True, timeout=5)
        elif action in {"mute", "toggle_mute"}:
            subprocess.run(["osascript", "-e", "set volume with output muted"], check=True, capture_output=True, text=True, timeout=5)
        elif action == "unmute":
            subprocess.run(["osascript", "-e", "set volume without output muted"], check=True, capture_output=True, text=True, timeout=5)
        elif action == "open_settings":
            subprocess.Popen(["open", "-a", "System Settings"])
        elif action in {"task_manager", "activity_monitor"}:
            subprocess.Popen(["open", "-a", "Activity Monitor"])
        elif action == "lock_screen":
            subprocess.run(["pmset", "displaysleepnow"], check=False, capture_output=True, text=True, timeout=5)
        elif action == "sleep_display":
            subprocess.run(["pmset", "displaysleepnow"], check=False, capture_output=True, text=True, timeout=5)
        elif action == "dark_mode":
            subprocess.run(
                ["osascript", "-e", 'tell app "System Events" to tell appearance preferences to set dark mode to not dark mode'],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        elif action in {"new_tab", "close_tab", "refresh_page", "switch_window", "show_desktop", "copy", "paste", "cut", "undo", "redo", "select_all", "save", "enter", "escape"}:
            pg = _pyautogui()
            hotkeys = {
                "new_tab": ("command", "t"),
                "close_tab": ("command", "w"),
                "refresh_page": ("command", "r"),
                "switch_window": ("command", "tab"),
                "show_desktop": ("fn", "f11"),
                "copy": ("command", "c"),
                "paste": ("command", "v"),
                "cut": ("command", "x"),
                "undo": ("command", "z"),
                "redo": ("command", "shift", "z"),
                "select_all": ("command", "a"),
                "save": ("command", "s"),
            }
            if action in hotkeys:
                pg.hotkey(*hotkeys[action])
            else:
                pg.press("enter" if action == "enter" else "escape")
        else:
            return _fail("computer_settings", f"Unknown settings action: {action}.")

        return _ok("computer_settings", action=action, output=f"Completed {action}.")
    except Exception as e:
        return _fail("computer_settings", str(e), action=action)


def computer_control(
    action: str,
    text: str = "",
    x: int | None = None,
    y: int | None = None,
    keys: str = "",
    key: str = "enter",
    direction: str = "down",
    amount: int = 3,
    seconds: float = 1.0,
    path: str = "",
    clear_first: bool = True,
) -> dict[str, Any]:
    action = action.strip().lower().replace("-", "_")

    try:
        pg = _pyautogui()
        clip = _pyperclip()

        if action in {"type", "smart_type"}:
            if clear_first and action == "smart_type":
                pg.hotkey("command", "a")
                pg.press("delete")
            if clip:
                clip.copy(text)
                pg.hotkey("command", "v")
            else:
                pg.write(text, interval=0.02)
        elif action in {"click", "left_click"}:
            pg.click(x=x, y=y)
        elif action == "double_click":
            pg.click(x=x, y=y, clicks=2)
        elif action == "right_click":
            pg.click(x=x, y=y, button="right")
        elif action == "hotkey":
            pg.hotkey(*[part.strip() for part in keys.split("+") if part.strip()])
        elif action == "press":
            pg.press(key)
        elif action == "scroll":
            pg.scroll(abs(int(amount)) if direction == "up" else -abs(int(amount)))
        elif action == "screenshot":
            target = _resolve_path(path or "desktop", f"dexter_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png" if not path else "")
            image = pg.screenshot()
            image.save(str(target))
            return _ok("computer_control", action=action, output=f"Screenshot saved: {target}", path=str(target))
        elif action == "wait":
            time.sleep(min(float(seconds), 30.0))
        elif action == "copy":
            pg.hotkey("command", "c")
            time.sleep(0.1)
            copied = clip.paste() if clip else ""
            return _ok("computer_control", action=action, output=copied)
        elif action == "paste":
            if clip:
                clip.copy(text)
            pg.hotkey("command", "v")
        else:
            return _fail("computer_control", f"Unknown computer action: {action}.")

        return _ok("computer_control", action=action, output=f"Completed {action}.")
    except Exception as e:
        return _fail("computer_control", str(e), action=action)


def screen_process(text: str = "Describe the screen.", angle: str = "screen") -> dict[str, Any]:
    try:
        pg = _pyautogui()
        target = _resolve_path("desktop", f"dexter_screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        image = pg.screenshot()
        image.save(str(target))
        return _ok("screen_process", output=f"Captured screen for: {text}", path=str(target), angle=angle)
    except Exception as e:
        return _fail("screen_process", str(e))


def send_message(
    receiver: str,
    message_text: str,
    platform: str = "messages",
    auto_send: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    receiver = receiver.strip()
    message_text = message_text.strip()
    clean_platform = (platform or "messages").strip().lower()

    if not receiver or not message_text:
        return _fail("send_message", "receiver and message_text are required.")

    if clean_platform in {"text", "sms", "imessage", "message", "messages"}:
        clean_platform = "messages"
    elif clean_platform in {"whatsapp", "whats app", "wa"}:
        clean_platform = "whatsapp"
    elif clean_platform in {"email", "mail", "mailto"}:
        clean_platform = "mailto"

    if dry_run:
        return _ok(
            "send_message",
            platform=clean_platform,
            receiver=receiver,
            status="dry_run",
            sent=False,
            output=f"Dry run: would prepare {clean_platform} message to {receiver}.",
        )

    try:
        if clean_platform == "whatsapp":
            return _open_whatsapp_message(receiver, message_text, auto_send=auto_send)

        if clean_platform == "messages":
            if auto_send:
                return _send_imessage(receiver, message_text)

            subprocess.Popen(["open", "-a", "Messages"])
            return _ok(
                "send_message",
                platform="messages",
                receiver=receiver,
                status="drafted",
                sent=False,
                output=f"Opened Messages. Draft this to {receiver}: {message_text}",
            )

        if clean_platform == "mailto":
            mailto = f"mailto:{urllib.parse.quote(receiver)}?body={urllib.parse.quote(message_text)}"
            _open_url(mailto)
            return _ok(
                "send_message",
                platform="mailto",
                receiver=receiver,
                status="drafted",
                sent=False,
                output=f"Opened mail draft for {receiver}. Review it and press Send.",
            )

        query = urllib.parse.quote_plus(f"{clean_platform} message {receiver}")
        _open_url(f"https://www.google.com/search?q={query}", app="Brave Browser")
        return _ok(
            "send_message",
            platform=clean_platform,
            receiver=receiver,
            status="unsupported_platform",
            sent=False,
            output=(
                f"I do not have a direct {clean_platform} sender yet. "
                f"Opened a browser search for messaging {receiver} on {clean_platform}."
            ),
        )
    except Exception as e:
        return _fail("send_message", str(e), receiver=receiver, platform=clean_platform, sent=False)


def flight_finder(origin: str, destination: str, date: str = "") -> dict[str, Any]:
    query = f"flights from {origin} to {destination} {date}".strip()
    try:
        result = web_search_tool.web_search(query=query, max_results=5)
        if result.get("ok"):
            return _ok("flight_finder", output=f"Found flight search results for {origin} to {destination}.", results=result.get("results", []))
        return _fail("flight_finder", result.get("error", "Flight search failed."))
    except Exception as e:
        return _fail("flight_finder", str(e))


def game_updater(
    action: str = "list",
    platform: str = "steam",
    game_name: str = "",
    shutdown_when_done: bool = False,
) -> dict[str, Any]:
    action = action.strip().lower()
    platform = platform.strip().lower()

    try:
        if platform in {"steam", "both"}:
            subprocess.Popen(["open", "steam://open/downloads"])
        if platform in {"epic", "both"}:
            subprocess.Popen(["open", "-a", "Epic Games Launcher"])

        extra = " Shutdown was not scheduled; Dexter requires explicit confirmation for that." if shutdown_when_done else ""
        return _ok("game_updater", action=action, output=f"Opened {platform} game update/downloads view for {game_name or 'your games'}.{extra}")
    except Exception as e:
        return _fail("game_updater", str(e), action=action)


def file_processor(action: str, file_path: str, instruction: str = "") -> dict[str, Any]:
    action = action.strip().lower()

    try:
        target = _resolve_path(file_path)
        if not target.exists() or not target.is_file():
            return _fail("file_processor", "File not found.", file_path=file_path)

        content = target.read_text(encoding="utf-8", errors="replace")[:12000]

        if action in {"summarize", "analyze", "extract"}:
            prompt = instruction or f"{action.title()} this file clearly and concisely."
            output = chat_with_ollama(f"{prompt}\n\nFile: {target.name}\n\n{content}")
            return _ok("file_processor", action=action, output=output, path=str(target))

        if action == "convert_to_text":
            return _ok("file_processor", action=action, output=content, path=str(target))

        return _fail("file_processor", f"Unknown file processor action: {action}.")
    except Exception as e:
        return _fail("file_processor", str(e), action=action)


def code_helper(action: str, description: str = "", language: str = "python", file_path: str = "", output_path: str = "") -> dict[str, Any]:
    action = action.strip().lower()

    try:
        if action == "run":
            if not file_path:
                return _fail("code_helper", "file_path is required to run code.")
            target = _resolve_path(file_path)
            if target.suffix.lower() != ".py":
                return _fail("code_helper", "Only Python files can be run directly right now.")
            completed = subprocess.run(
                [sys.executable, str(target)],
                cwd=str(target.parent),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if completed.returncode != 0:
                return _fail("code_helper", completed.stderr.strip() or "Code execution failed.", path=str(target))
            return _ok("code_helper", action=action, output=completed.stdout.strip() or "Code ran successfully.", path=str(target))

        if action in {"explain", "review"}:
            target = _resolve_path(file_path)
            content = target.read_text(encoding="utf-8", errors="replace")[:12000]
            output = chat_with_ollama(f"{action.title()} this {language} code:\n\n{content}")
            return _ok("code_helper", action=action, output=output, path=str(target))

        if action in {"write", "edit"}:
            prompt = (
                f"Write {language} code for this request. Return only code, no markdown:\n{description}"
                if action == "write"
                else f"Suggest a concise edit plan for this file request:\n{description}"
            )
            output = chat_with_ollama(prompt)
            if output_path and action == "write":
                target = _resolve_path(output_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(output, encoding="utf-8")
                return _ok("code_helper", action=action, output=f"Wrote code to {target}.", path=str(target))
            return _ok("code_helper", action=action, output=output)

        return _fail("code_helper", f"Unknown code helper action: {action}.")
    except Exception as e:
        return _fail("code_helper", str(e), action=action)


def dev_agent(description: str, language: str = "", path: str = "project") -> dict[str, Any]:
    try:
        project = _resolve_path(path)
        prompt = (
            "You are Dexter's local dev helper. Produce a concise implementation plan "
            "using this project context only. Do not claim to have edited files.\n\n"
            f"Project: {project}\nLanguage: {language or 'auto'}\nTask: {description}"
        )
        output = chat_with_ollama(prompt)
        return _ok("dev_agent", output=output, path=str(project))
    except Exception as e:
        return _fail("dev_agent", str(e))
