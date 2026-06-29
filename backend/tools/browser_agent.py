from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

from backend.tools.safe_paths import PROJECT_ROOT, resolve_safe_path
from backend.utils.logger import log_action


USER_HOME_DIR = Path(os.getenv("DEXTER_BROWSER_HOME") or Path.home()).expanduser().resolve()
PROFILE_DIR = Path(
    os.getenv("DEXTER_BROWSER_PROFILE_DIR")
    or os.getenv("DEXTER_BRAVE_PROFILE_DIR")
    or PROJECT_ROOT / "data" / "brave_profile"
).expanduser().resolve()
SCREENSHOT_DIR = PROJECT_ROOT / "data" / "screenshots"

BRAVE_MAIN_PROFILE_DIR = USER_HOME_DIR / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser"
CHROME_MAIN_PROFILE_DIR = USER_HOME_DIR / "Library" / "Application Support" / "Google" / "Chrome"

BROWSER_EXECUTABLE_CANDIDATES = [
    os.getenv("DEXTER_BROWSER_EXECUTABLE", "").strip(),
    os.getenv("DEXTER_BRAVE_EXECUTABLE", "").strip(),
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    str(USER_HOME_DIR / "Applications" / "Brave Browser.app" / "Contents" / "MacOS" / "Brave Browser"),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    str(USER_HOME_DIR / "Applications" / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome"),
]

_LOCK = threading.RLock()
_PLAYWRIGHT = None
_BROWSER = None
_CONTEXT = None
_PAGE = None
_OWNER_THREAD_ID = None
_BROWSER_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dexter-browser")
_BROWSER_WORKER_THREAD_ID = None
_BROWSER_THREAD_LOCAL = threading.local()

T = TypeVar("T")


def _ok(**payload: Any) -> dict[str, Any]:
    result = {"ok": True, "tool": "browser_agent", **payload}
    log_action("browser_agent", result)
    return result


def _fail(error: str, **payload: Any) -> dict[str, Any]:
    result = {"ok": False, "tool": "browser_agent", "error": error, **payload}
    log_action("browser_agent_error", result)
    return result


def _playwright_status() -> tuple[bool, str]:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401

        return True, ""
    except Exception as e:
        return False, str(e)


def _browser_connection_mode() -> str:
    mode = (
        os.getenv("DEXTER_BROWSER_CONNECTION")
        or os.getenv("DEXTER_BRAVE_CONNECTION")
        or "persistent"
    ).strip().lower()
    if mode in {"cdp", "remote", "attach", "current"}:
        return "cdp"
    return "persistent"


def _browser_cdp_url() -> str:
    return (
        os.getenv("DEXTER_BROWSER_CDP_URL")
        or os.getenv("DEXTER_BRAVE_CDP_URL")
        or "http://127.0.0.1:9222"
    ).strip()


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _browser_cdp_reachable(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if not parsed.hostname:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((parsed.hostname, port), timeout=0.25):
            return True
    except OSError:
        return False


def _cdp_host_port(url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port


def _browser_app_name() -> str:
    configured = os.getenv("DEXTER_BROWSER_APP_NAME", "").strip()
    if configured:
        return configured

    executable = os.getenv("DEXTER_BROWSER_EXECUTABLE", "").strip()
    if "Google Chrome" in executable:
        return "Google Chrome"
    return "Brave Browser"


def _local_cdp_url(url: str) -> bool:
    host, _ = _cdp_host_port(url)
    return host in {"127.0.0.1", "localhost", "::1"}


def _wait_for_cdp_browser(url: str, timeout_seconds: float | int = 10) -> bool:
    deadline = time.time() + min(max(float(timeout_seconds), 3), 15)
    while time.time() < deadline:
        if _browser_cdp_reachable(url):
            return True
        time.sleep(0.35)
    return _browser_cdp_reachable(url)


def _cdp_launch_command(app_name: str, port: int) -> list[str]:
    return [
        "open",
        "-a",
        app_name,
        "--args",
        f"--remote-debugging-port={port}",
        "--restore-last-session",
        "--no-first-run",
        "--no-default-browser-check",
    ]


def _cdp_direct_launch_command(port: int) -> list[str]:
    return [
        _browser_executable(),
        f"--remote-debugging-port={port}",
        "--restore-last-session",
        "--no-first-run",
        "--no-default-browser-check",
    ]


def _browser_process_running(app_name: str) -> bool:
    completed = subprocess.run(
        ["pgrep", "-x", app_name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=3,
    )
    return completed.returncode == 0


def _wait_for_browser_quit(app_name: str, timeout_seconds: float | int = 15) -> bool:
    deadline = time.time() + min(max(float(timeout_seconds), 3), 20)
    while time.time() < deadline:
        if not _browser_process_running(app_name):
            return True
        time.sleep(0.35)
    return not _browser_process_running(app_name)


def _auto_launch_cdp_browser(url: str, timeout_seconds: float | int = 10) -> None:
    if not _env_flag("DEXTER_BROWSER_AUTO_LAUNCH_CDP", default=False):
        return

    host, port = _cdp_host_port(url)
    if not _local_cdp_url(url):
        return

    app_name = _browser_app_name()
    command = _cdp_launch_command(app_name, port)
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _wait_for_cdp_browser(url, timeout_seconds=timeout_seconds)


def _relaunch_existing_cdp_browser(url: str, timeout_seconds: float | int = 15) -> bool:
    if not _local_cdp_url(url):
        return False

    _, port = _cdp_host_port(url)
    app_name = _browser_app_name()
    subprocess.run(
        ["osascript", "-e", f"tell application {json.dumps(app_name)} to quit"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    _wait_for_browser_quit(app_name, timeout_seconds=timeout_seconds)
    if _browser_process_running(app_name) and _env_flag("DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING", default=False):
        subprocess.run(
            ["pkill", "-x", app_name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        try:
            executable = _browser_executable()
        except Exception:
            executable = ""
        if executable:
            subprocess.run(
                ["pkill", "-f", executable],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        _wait_for_browser_quit(app_name, timeout_seconds=timeout_seconds)
    reset_browser_agent_state()
    subprocess.Popen(_cdp_direct_launch_command(port), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return _wait_for_cdp_browser(url, timeout_seconds=timeout_seconds)


def _browser_executable() -> str:
    for candidate in BROWSER_EXECUTABLE_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    raise FileNotFoundError("A supported Chromium browser executable was not found.")


def _fallback_profile_dir() -> Path:
    configured = os.getenv("DEXTER_BROWSER_FALLBACK_PROFILE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (PROJECT_ROOT / "data" / "brave_profile").resolve()


def _timeout_ms(timeout_seconds: float | int) -> int:
    return int(max(1, float(timeout_seconds)) * 1000)


def _current_thread_id() -> int:
    return threading.get_ident()


def _call_on_browser_thread(func: Callable[..., T], args: tuple[Any, ...], kwargs: dict[str, Any]) -> T:
    global _BROWSER_WORKER_THREAD_ID

    _BROWSER_WORKER_THREAD_ID = _current_thread_id()
    _BROWSER_THREAD_LOCAL.in_browser_worker = True
    try:
        return func(*args, **kwargs)
    finally:
        _BROWSER_THREAD_LOCAL.in_browser_worker = False


def run_on_browser_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run sync Playwright work away from FastAPI's asyncio event loop."""

    if getattr(_BROWSER_THREAD_LOCAL, "in_browser_worker", False):
        return func(*args, **kwargs)

    future = _BROWSER_EXECUTOR.submit(_call_on_browser_thread, func, args, kwargs)
    return future.result()


def _discard_browser_handles() -> None:
    global _PLAYWRIGHT, _BROWSER, _CONTEXT, _PAGE, _OWNER_THREAD_ID

    _PLAYWRIGHT = None
    _BROWSER = None
    _CONTEXT = None
    _PAGE = None
    _OWNER_THREAD_ID = None


def reset_browser_agent_state() -> None:
    """Forget cached Playwright handles so the next browser action reconnects."""

    _discard_browser_handles()


def _discard_if_wrong_thread() -> None:
    global _OWNER_THREAD_ID

    current = _current_thread_id()
    if _OWNER_THREAD_ID is not None and _OWNER_THREAD_ID != current:
        # Playwright's sync API is thread-affine. Do not close handles from a
        # different thread; just forget them and reconnect on this request.
        _discard_browser_handles()


def _runtime_ready() -> dict[str, Any]:
    _discard_if_wrong_thread()

    playwright_available, playwright_error = _playwright_status()
    browser_path = ""
    browser_error = ""
    try:
        browser_path = _browser_executable()
    except Exception as e:
        browser_error = str(e)

    connection_mode = _browser_connection_mode()
    cdp_url = _browser_cdp_url() if connection_mode == "cdp" else ""
    cdp_reachable = _browser_cdp_reachable(cdp_url) if cdp_url else False
    cdp_auto_launch_enabled = _env_flag("DEXTER_BROWSER_AUTO_LAUNCH_CDP", default=False)
    cdp_relaunch_existing_enabled = _env_flag("DEXTER_BROWSER_CDP_RELAUNCH_EXISTING", default=False)
    cdp_force_quit_existing_enabled = _env_flag("DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING", default=False)
    cdp_fallback_persistent_enabled = _env_flag("DEXTER_BROWSER_CDP_FALLBACK_PERSISTENT", default=False)
    cdp_recoverable = (
        connection_mode == "cdp"
        and bool(browser_path)
        and (cdp_auto_launch_enabled or cdp_fallback_persistent_enabled)
    )

    return {
        "playwright_available": playwright_available,
        "playwright_error": playwright_error,
        "browser_connection": connection_mode,
        "browser_available": bool(browser_path),
        "browser_path": browser_path,
        "browser_error": browser_error,
        "brave_available": bool(browser_path),
        "brave_path": browser_path,
        "brave_error": browser_error,
        "cdp_url": cdp_url,
        "cdp_reachable": cdp_reachable,
        "cdp_auto_launch_enabled": cdp_auto_launch_enabled,
        "cdp_relaunch_existing_enabled": cdp_relaunch_existing_enabled,
        "cdp_force_quit_existing_enabled": cdp_force_quit_existing_enabled,
        "cdp_fallback_persistent_enabled": cdp_fallback_persistent_enabled,
        "fallback_profile_dir": str(_fallback_profile_dir()),
        "profile_dir": str(PROFILE_DIR),
        "profile_exists": PROFILE_DIR.exists(),
        "known_main_profiles": {
            "brave": str(BRAVE_MAIN_PROFILE_DIR),
            "brave_exists": BRAVE_MAIN_PROFILE_DIR.exists(),
            "chrome": str(CHROME_MAIN_PROFILE_DIR),
            "chrome_exists": CHROME_MAIN_PROFILE_DIR.exists(),
        },
        "running": _CONTEXT is not None,
        "owner_thread": _OWNER_THREAD_ID,
        "current_thread": _current_thread_id(),
        "runtime_ready": playwright_available
        and (
            (connection_mode == "cdp" and (cdp_reachable or cdp_recoverable))
            or (connection_mode != "cdp" and bool(browser_path))
        ),
    }


def _ensure_page(timeout_seconds: float | int = 20):
    global _PLAYWRIGHT, _BROWSER, _CONTEXT, _PAGE, _OWNER_THREAD_ID

    _discard_if_wrong_thread()

    if _CONTEXT is not None and _PAGE is not None:
        try:
            if not _PAGE.is_closed():
                _PAGE.title()
                return _PAGE
        except Exception:
            _discard_browser_handles()

    playwright_available, playwright_error = _playwright_status()
    if not playwright_available:
        raise RuntimeError(
            "Playwright is not installed in Dexter's backend environment. "
            "Run `./.venv/bin/python -m pip install playwright`."
            + (f" Details: {playwright_error}" if playwright_error else "")
        )

    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    if _PLAYWRIGHT is None:
        _PLAYWRIGHT = sync_playwright().start()
        _OWNER_THREAD_ID = _current_thread_id()

    if _browser_connection_mode() == "cdp":
        cdp_url = _browser_cdp_url()
        if not _browser_cdp_reachable(cdp_url):
            _auto_launch_cdp_browser(cdp_url, timeout_seconds=timeout_seconds)
        if not _browser_cdp_reachable(cdp_url) and not _env_flag("DEXTER_BROWSER_CDP_FALLBACK_PERSISTENT", default=False):
            raise RuntimeError(
                "Dexter is configured to use your existing Brave session only, but it cannot attach to it yet. "
                f"Brave must be running with remote debugging enabled at {cdp_url}. "
                "Dexter will not quit or relaunch Brave during normal browser actions. "
                "To attach without closing Brave, start Brave with: "
                "open -a 'Brave Browser' --args --remote-debugging-port=9222 --restore-last-session."
            )
        try:
            _BROWSER = _PLAYWRIGHT.chromium.connect_over_cdp(
                cdp_url,
                timeout=_timeout_ms(timeout_seconds),
            )
        except Exception as e:
            _BROWSER = None
            _CONTEXT = None
            _PAGE = None
            if _env_flag("DEXTER_BROWSER_CDP_FALLBACK_PERSISTENT", default=False):
                try:
                    return _launch_persistent_page(timeout_seconds=timeout_seconds, profile_dir=_fallback_profile_dir())
                except Exception as fallback_error:
                    raise RuntimeError(
                        "Could not attach to your current browser session or open Dexter's fallback browser profile. "
                        f"CDP attach failed at {cdp_url}: {e}. "
                        f"Fallback launch failed: {fallback_error}"
                    ) from fallback_error
            raise RuntimeError(
                "Dexter is configured to use your existing Brave session only, but it could not attach. "
                f"Start Brave or Chrome with remote debugging enabled at {cdp_url}, then try again. "
                "Example: open -a 'Brave Browser' --args --remote-debugging-port=9222 --restore-last-session"
            ) from e

        if not _BROWSER.contexts:
            _CONTEXT = _BROWSER.new_context(viewport={"width": 1400, "height": 900})
        else:
            _CONTEXT = _BROWSER.contexts[0]
        pages = [candidate for candidate in _CONTEXT.pages if not candidate.is_closed()]
        _PAGE = pages[-1] if pages else _CONTEXT.new_page()
        _PAGE.set_default_timeout(_timeout_ms(timeout_seconds))
        _OWNER_THREAD_ID = _current_thread_id()
        return _PAGE

    return _launch_persistent_page(timeout_seconds=timeout_seconds, profile_dir=PROFILE_DIR)


def _launch_persistent_page(timeout_seconds: float | int = 20, profile_dir: Path = PROFILE_DIR):
    global _PLAYWRIGHT, _CONTEXT, _PAGE, _OWNER_THREAD_ID

    profile_dir = Path(profile_dir).expanduser().resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    if _PLAYWRIGHT is None:
        from playwright.sync_api import sync_playwright

        _PLAYWRIGHT = sync_playwright().start()
        _OWNER_THREAD_ID = _current_thread_id()

    try:
        _CONTEXT = _PLAYWRIGHT.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            executable_path=_browser_executable(),
            headless=False,
            accept_downloads=True,
            viewport={"width": 1400, "height": 900},
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-default-apps",
                "--disable-features=Translate",
            ],
            timeout=_timeout_ms(timeout_seconds),
        )
    except Exception as e:
        _discard_browser_handles()
        raise RuntimeError(f"Could not launch Dexter-controlled browser: {e}") from e

    _PAGE = _CONTEXT.pages[0] if _CONTEXT.pages else _CONTEXT.new_page()
    _PAGE.set_default_timeout(_timeout_ms(timeout_seconds))
    _OWNER_THREAD_ID = _current_thread_id()
    return _PAGE


def _visible_text(page, max_chars: int = 4000) -> str:
    try:
        return page.evaluate(
            """(maxChars) => (document.body?.innerText || '').slice(0, maxChars)""",
            max_chars,
        )
    except Exception:
        return ""


def _page_state(page, max_chars: int = 1500) -> dict[str, Any]:
    return {
        "title": page.title(),
        "url": page.url,
        "text": _visible_text(page, max_chars=max_chars),
    }


def _save_screenshot(page, requested_path: str = "") -> str:
    if requested_path:
        target = resolve_safe_path(requested_path)
    else:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        target = SCREENSHOT_DIR / f"browser_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(target), full_page=False)
    return str(target)


def _goto(page, url: str, timeout_seconds: float | int) -> None:
    destination = url.strip()
    if destination and "://" not in destination:
        destination = "https://" + destination
    page.goto(destination or "about:blank", wait_until="domcontentloaded", timeout=_timeout_ms(timeout_seconds))


def _first_visible_locator(page, selectors: list[str]):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() > 0 and locator.is_visible(timeout=700):
                return locator, selector
        except Exception:
            continue
    return None, ""


def _whatsapp_login_required(text: str) -> bool:
    lower = text.lower()
    return any(
        phrase in lower
        for phrase in (
            "use whatsapp on your computer",
            "log in to whatsapp web",
            "scan to log in",
            "scan the qr code",
            "scan this qr code",
            "link a device",
            "link with phone number",
            "log in with phone number",
        )
    )


def _whatsapp_invalid_number(text: str) -> bool:
    lower = text.lower()
    return "phone number shared via url is invalid" in lower or "invalid phone number" in lower


WHATSAPP_ATTACH_SELECTORS = [
    "button[aria-label='Attach']",
    "button[title='Attach']",
    "div[title='Attach']",
    "span[data-icon='clip']",
    "span[data-icon='plus']",
    "span[data-icon='plus-rounded']",
    "span[data-icon='attach-menu-plus']",
]

WHATSAPP_DOCUMENT_SELECTORS = [
    "button[role='menuitem'][aria-label='Document']",
    "button[aria-label='Document']",
    "[role='menuitem'][aria-label='Document']",
    "div[role='button'][aria-label='Document']",
]

WHATSAPP_CHAT_READY_SELECTORS = [
    "footer div[contenteditable='true'][role='textbox']",
    *WHATSAPP_ATTACH_SELECTORS,
]

WHATSAPP_SEARCH_SELECTORS = [
    "div[contenteditable='true'][aria-label='Search or start new chat']",
    "div[role='textbox'][aria-label='Search or start new chat']",
    "div[contenteditable='true'][aria-label='Search input textbox']",
    "div[role='textbox'][aria-label='Search input textbox']",
    "div[contenteditable='true'][title='Search input textbox']",
    "div[contenteditable='true'][aria-label*='Search']",
    "div[role='textbox'][aria-label*='Search']",
    "div[contenteditable='true'][aria-label='Search']",
    "div[contenteditable='true'][data-tab='3']",
]

WHATSAPP_SEARCH_BUTTON_SELECTORS = [
    "button[aria-label='Search or start new chat']",
    "button[aria-label='Search']",
    "div[aria-label='Search or start new chat'][role='button']",
    "div[aria-label='Search'][role='button']",
    "span[data-icon='search']",
]

WHATSAPP_CHAT_ROW_SELECTORS = [
    "div[role='listitem']",
    "div[role='gridcell']",
    "div[tabindex='0']",
]

WHATSAPP_MESSAGE_BOX_SELECTORS = [
    "footer div[contenteditable='true'][role='textbox']",
    "footer div[contenteditable='true']",
    "div[aria-label='Type a message'][contenteditable='true']",
]

WHATSAPP_SEND_SELECTORS = [
    "div[aria-label='Send'][role='button']",
    "button[aria-label='Send']",
    "div[role='button'][aria-label='Send']",
    "span[data-icon='send']",
]

WHATSAPP_CAPTION_SELECTORS = [
    "div[aria-label='Add a caption'][contenteditable='true']",
    "div[role='textbox'][aria-label='Add a caption']",
    "div[contenteditable='true'][aria-placeholder='Add a caption']",
    "div[role='textbox'][aria-placeholder='Add a caption']",
    "div[data-testid='media-caption-input'][contenteditable='true']",
]


def _whatsapp_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return ""
    default_country = re.sub(r"\D", "", os.getenv("DEXTER_DEFAULT_COUNTRY_CODE", "1")) or "1"
    if len(digits) == 10:
        return f"{default_country}{digits}"
    return digits


def _whatsapp_other_window_blocked(text: str) -> bool:
    return "whatsapp is open in another window" in (text or "").lower()


def _whatsapp_file_attachment_rejected(text: str) -> bool:
    return "file you tried adding is not supported" in (text or "").lower()


def _whatsapp_accepts_document_upload(accept: str | None) -> bool:
    tokens = [token.strip().lower() for token in (accept or "").split(",") if token.strip()]
    if not tokens:
        return True

    media_prefixes = ("image/", "video/", "audio/")
    media_only = True
    for token in tokens:
        if token in {"*", "*/*"} or token.startswith(".") or token.startswith("application/"):
            return True
        if not token.startswith(media_prefixes):
            media_only = False
    return not media_only


def _whatsapp_prefer_existing_page(page, timeout_seconds: float | int):
    global _PAGE

    if _CONTEXT is None:
        return page

    try:
        pages = [candidate for candidate in _CONTEXT.pages if not candidate.is_closed()]
    except Exception:
        return page

    fallback = None
    for candidate in reversed(pages):
        try:
            if "web.whatsapp.com" not in (candidate.url or ""):
                continue
            text = _visible_text(candidate, max_chars=2500)
            if _whatsapp_other_window_blocked(text) or _whatsapp_login_required(text):
                continue
            if fallback is None:
                fallback = candidate
            ready_locator, _ = _first_visible_locator(candidate, WHATSAPP_CHAT_READY_SELECTORS)
            if ready_locator is None:
                continue
            candidate.set_default_timeout(_timeout_ms(timeout_seconds))
            _PAGE = candidate
            return candidate
        except Exception:
            continue

    if fallback is not None:
        try:
            fallback.set_default_timeout(_timeout_ms(timeout_seconds))
        except Exception:
            pass
        _PAGE = fallback
        return fallback

    return page


def _whatsapp_contact_candidates(receiver: str) -> list[str]:
    clean = re.sub(r"\s+", " ", receiver or "").strip()
    normalized = re.sub(r"^(?:my|the)\s+", "", clean, flags=re.I).strip()
    candidates = [normalized, clean] if normalized and normalized.lower() != clean.lower() else [clean]
    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate.lower() not in {item.lower() for item in unique}:
            unique.append(candidate)
    return unique


def _whatsapp_wait_for_app(page, timeout_seconds: float | int) -> str:
    for _ in range(24):
        text = _visible_text(page, max_chars=5000)
        if _whatsapp_login_required(text) or _whatsapp_invalid_number(text):
            break
        ready_locator, _ = _first_visible_locator(page, [*WHATSAPP_CHAT_READY_SELECTORS, *WHATSAPP_SEARCH_SELECTORS])
        if ready_locator is not None:
            break
        time.sleep(0.75)

    page_text = _visible_text(page, max_chars=6000)
    login_wait_seconds = float(os.getenv("DEXTER_BROWSER_LOGIN_WAIT_SECONDS", "180"))
    if _whatsapp_login_required(page_text) and login_wait_seconds > 0:
        deadline = time.time() + login_wait_seconds
        while time.time() < deadline:
            time.sleep(3)
            page_text = _visible_text(page, max_chars=6000)
            if not _whatsapp_login_required(page_text):
                break

    return page_text


def _whatsapp_type_into(locator, page, text: str, timeout_seconds: float | int) -> None:
    locator.click(timeout=_timeout_ms(timeout_seconds))
    try:
        locator.fill(text, timeout=_timeout_ms(timeout_seconds))
    except Exception:
        page.keyboard.press("Meta+A")
        page.keyboard.insert_text(text)


def _whatsapp_wait_for_chat_open(page, timeout_seconds: float | int) -> bool:
    deadline = time.time() + min(max(float(timeout_seconds), 4), 10)
    while time.time() < deadline:
        message_box, _ = _first_visible_locator(page, WHATSAPP_MESSAGE_BOX_SELECTORS)
        if message_box is not None:
            return True
        attach_button, _ = _first_visible_locator(page, WHATSAPP_ATTACH_SELECTORS)
        if attach_button is not None:
            return True
        time.sleep(0.35)
    return False


def _whatsapp_contact_pattern(candidate: str) -> re.Pattern[str]:
    return re.compile(rf"(^|\b){re.escape(candidate)}(\b|$)", re.I)


def _whatsapp_open_visible_chat(page, candidate: str, timeout_seconds: float | int) -> bool:
    pattern = _whatsapp_contact_pattern(candidate)
    locators = [
        page.get_by_title(re.compile(rf"^{re.escape(candidate)}$", re.I)).first,
        page.get_by_text(re.compile(rf"^{re.escape(candidate)}$", re.I)).first,
        page.get_by_title(pattern).first,
    ]

    for selector in WHATSAPP_CHAT_ROW_SELECTORS:
        locators.append(page.locator(selector).filter(has_text=pattern).first)

    for locator in locators:
        try:
            if locator.count() > 0 and locator.is_visible(timeout=900):
                locator.click(timeout=_timeout_ms(timeout_seconds))
                if _whatsapp_wait_for_chat_open(page, timeout_seconds):
                    return True
        except Exception:
            continue

    return False


def _whatsapp_open_chat(page, phone: str, receiver: str, timeout_seconds: float | int, text: str = "") -> tuple[str, str]:
    clean_phone = _whatsapp_phone(phone) or _whatsapp_phone(receiver)
    if clean_phone:
        encoded = urllib.parse.quote(text.strip()) if text.strip() else ""
        web_url = f"https://web.whatsapp.com/send?phone={clean_phone}"
        if encoded:
            web_url += f"&text={encoded}"
        _goto(page, web_url, timeout_seconds)
        return web_url, clean_phone

    candidates = _whatsapp_contact_candidates(receiver)
    if not candidates:
        raise RuntimeError("A WhatsApp phone number or contact name is required.")

    web_url = "https://web.whatsapp.com"
    if "web.whatsapp.com" not in (page.url or "") or _whatsapp_other_window_blocked(_visible_text(page, max_chars=1500)):
        _goto(page, web_url, timeout_seconds)
    page_text = _whatsapp_wait_for_app(page, timeout_seconds)
    if _whatsapp_login_required(page_text):
        return web_url, ""

    last_error = ""
    for candidate in candidates:
        if _whatsapp_open_visible_chat(page, candidate, timeout_seconds):
            return web_url, ""

        search_locator, _ = _first_visible_locator(page, WHATSAPP_SEARCH_SELECTORS)
        if search_locator is None:
            search_button, _ = _first_visible_locator(
                page,
                WHATSAPP_SEARCH_BUTTON_SELECTORS,
            )
            if search_button is not None:
                search_button.click(timeout=_timeout_ms(timeout_seconds))
                time.sleep(0.4)
                search_locator, _ = _first_visible_locator(page, WHATSAPP_SEARCH_SELECTORS)

        if search_locator is None:
            last_error = (
                f"Could not find a visible WhatsApp chat named {candidate}, "
                "and the WhatsApp Web contact search box was not available."
            )
            continue

        _whatsapp_type_into(search_locator, page, candidate, timeout_seconds)
        time.sleep(1.2)

        chat_locator = None
        for locator in (
            page.get_by_title(candidate, exact=False).first,
            page.locator("div[role='gridcell']").filter(has_text=candidate).first,
            page.get_by_text(candidate, exact=False).first,
        ):
            try:
                if locator.count() > 0 and locator.is_visible(timeout=900):
                    chat_locator = locator
                    break
            except Exception:
                continue

        if chat_locator is not None:
            chat_locator.click(timeout=_timeout_ms(timeout_seconds))
            for _ in range(12):
                message_box, _ = _first_visible_locator(page, WHATSAPP_MESSAGE_BOX_SELECTORS)
                if message_box is not None:
                    return web_url, ""
                time.sleep(0.5)
            last_error = f"Found {candidate} in WhatsApp search, but the chat did not open."
            continue

        last_error = f"Could not find a WhatsApp chat named {candidate}."

    raise RuntimeError(last_error or f"Could not find a WhatsApp chat named {receiver}.")


def _whatsapp_document_option(page):
    locators = [
        page.get_by_role("menuitem", name=re.compile(r"^Document$", re.I)).first,
        page.get_by_role("button", name=re.compile(r"^Document$", re.I)).first,
        page.get_by_text(re.compile(r"^Document$", re.I)).first,
    ]
    for selector in WHATSAPP_DOCUMENT_SELECTORS:
        locators.append(page.locator(selector).first)

    for locator in locators:
        try:
            if locator.count() > 0 and locator.is_visible(timeout=700):
                return locator
        except Exception:
            continue
    return None


def _whatsapp_document_file_input(page):
    file_inputs = page.locator("input[type='file']")
    count = file_inputs.count()
    for index in reversed(range(count)):
        candidate = file_inputs.nth(index)
        try:
            if _whatsapp_accepts_document_upload(candidate.get_attribute("accept")):
                return candidate
        except Exception:
            continue
    raise RuntimeError("WhatsApp Document attachment input was not available.")


def _whatsapp_attach_document_file(page, target_file: Path, timeout_seconds: float | int) -> str:
    document_locator = _whatsapp_document_option(page)
    if document_locator is None:
        attach_locator, _ = _first_visible_locator(
            page,
            WHATSAPP_ATTACH_SELECTORS,
        )
        if attach_locator is None:
            raise RuntimeError("WhatsApp attachment button was not available.")
        attach_locator.click(timeout=_timeout_ms(timeout_seconds))
        time.sleep(0.5)
        document_locator = _whatsapp_document_option(page)

    if document_locator is not None:
        try:
            with page.expect_file_chooser(timeout=_timeout_ms(min(float(timeout_seconds), 8))) as file_chooser_info:
                document_locator.click(timeout=_timeout_ms(timeout_seconds))
            file_chooser_info.value.set_files(str(target_file), timeout=_timeout_ms(timeout_seconds))
            return "Document file chooser"
        except Exception:
            pass

    input_locator = _whatsapp_document_file_input(page)
    input_locator.set_input_files(str(target_file), timeout=_timeout_ms(timeout_seconds))
    return "Document input"


def browser_agent(
    action: str = "status",
    url: str = "",
    query: str = "",
    text: str = "",
    selector: str = "",
    button_text: str = "",
    key: str = "Enter",
    direction: str = "down",
    amount: int = 5,
    wait_seconds: float = 0.5,
    timeout_seconds: float = 20,
    screenshot_path: str = "",
) -> dict[str, Any]:
    """Control Dexter's own Brave browser session."""

    global _PAGE

    clean_action = (action or "status").strip().lower().replace("-", "_")

    if clean_action == "status":
        status = _runtime_ready()
        return _ok(action=clean_action, output="Dexter browser agent status checked.", **status)

    with _LOCK:
        try:
            if clean_action in {"close", "shutdown"}:
                close_browser_agent()
                return _ok(action=clean_action, output="Closed Dexter-controlled Brave session.")

            if clean_action in {
                "attach_existing_session",
                "reconnect_existing_session",
                "reuse_existing_session",
                "enable_existing_session",
            }:
                if _browser_connection_mode() != "cdp":
                    return _fail(
                        "Existing-session attach requires DEXTER_BROWSER_CONNECTION=cdp.",
                        action=clean_action,
                    )
                cdp_url = _browser_cdp_url()
                _discard_browser_handles()
                if not _browser_cdp_reachable(cdp_url):
                    return _fail(
                        (
                            "Could not attach to the existing browser session because the CDP port is not reachable. "
                            f"Dexter did not quit or relaunch Brave. Start Brave with remote debugging at {cdp_url}, "
                            "then try again."
                        ),
                        action=clean_action,
                        **_runtime_ready(),
                    )
                page = _ensure_page(timeout_seconds=timeout_seconds)
                return _ok(
                    action=clean_action,
                    output="Attached to the existing browser session without quitting or relaunching Brave.",
                    **_page_state(page),
                    **_runtime_ready(),
                )

            if clean_action == "relaunch_existing_session":
                if _browser_connection_mode() != "cdp":
                    return _fail(
                        "Existing-session relaunch requires DEXTER_BROWSER_CONNECTION=cdp.",
                        action=clean_action,
                    )
                cdp_url = _browser_cdp_url()
                relaunched = _relaunch_existing_cdp_browser(cdp_url, timeout_seconds=timeout_seconds)
                status = _runtime_ready()
                if relaunched:
                    return _ok(
                        action=clean_action,
                        output=(
                            "Reopened the existing browser profile with remote debugging. "
                            "Dexter can now attach to the signed-in session."
                        ),
                        **status,
                    )
                return _fail(
                    "Could not reopen the existing browser profile with remote debugging.",
                    action=clean_action,
                    **status,
                )

            page = _ensure_page(timeout_seconds=timeout_seconds)

            if clean_action == "new_tab":
                if _CONTEXT is None:
                    return _fail("Browser context is not available.", action=clean_action)
                _PAGE = _CONTEXT.new_page()
                return _ok(action=clean_action, output="Opened a new Dexter browser tab.", **_page_state(_PAGE))

            if clean_action in {"close_tab", "close_current_tab"}:
                page.close()
                if _CONTEXT is not None and _CONTEXT.pages:
                    _PAGE = _CONTEXT.pages[-1]
                    return _ok(action=clean_action, output="Closed current Dexter browser tab.", **_page_state(_PAGE))
                _PAGE = None
                return _ok(action=clean_action, output="Closed current Dexter browser tab.")

            if clean_action in {"reload", "refresh"}:
                page.reload(wait_until="domcontentloaded", timeout=_timeout_ms(timeout_seconds))
                return _ok(action=clean_action, output="Reloaded current Dexter browser page.", **_page_state(page))

            if clean_action == "back":
                page.go_back(wait_until="domcontentloaded", timeout=_timeout_ms(timeout_seconds))
                return _ok(action=clean_action, output="Went back in Dexter browser.", **_page_state(page))

            if clean_action == "forward":
                page.go_forward(wait_until="domcontentloaded", timeout=_timeout_ms(timeout_seconds))
                return _ok(action=clean_action, output="Went forward in Dexter browser.", **_page_state(page))

            if clean_action in {"open_url", "go_to", "navigate"}:
                _goto(page, url, timeout_seconds)
                time.sleep(max(0, wait_seconds))
                return _ok(action=clean_action, output=f"Opened {page.url}", **_page_state(page))

            if clean_action == "search":
                clean_query = (query or text).strip()
                if not clean_query:
                    return _fail("Search query is required.", action=clean_action)
                destination = "https://www.google.com/search?q=" + urllib.parse.quote_plus(clean_query)
                _goto(page, destination, timeout_seconds)
                return _ok(action=clean_action, output=f"Searched for {clean_query}.", **_page_state(page))

            if clean_action in {"inspect", "read_page"}:
                return _ok(action=clean_action, output="Inspected current browser page.", **_page_state(page, max_chars=6000))

            if clean_action in {"click_text", "click_button"}:
                target_text = (button_text or text).strip()
                if not target_text:
                    return _fail("button_text or text is required for click_text.", action=clean_action)
                page.get_by_text(target_text, exact=False).first.click(timeout=_timeout_ms(timeout_seconds))
                time.sleep(max(0, wait_seconds))
                return _ok(action=clean_action, output=f"Clicked text: {target_text}", **_page_state(page))

            if clean_action == "click_selector":
                if not selector:
                    return _fail("selector is required for click_selector.", action=clean_action)
                page.locator(selector).first.click(timeout=_timeout_ms(timeout_seconds))
                time.sleep(max(0, wait_seconds))
                return _ok(action=clean_action, output=f"Clicked selector: {selector}", **_page_state(page))

            if clean_action in {"type", "type_text"}:
                if not text:
                    return _fail("text is required for type.", action=clean_action)
                if selector:
                    page.locator(selector).first.fill(text, timeout=_timeout_ms(timeout_seconds))
                else:
                    page.keyboard.insert_text(text)
                return _ok(action=clean_action, output="Typed text in browser.", **_page_state(page))

            if clean_action == "press":
                page.keyboard.press(key)
                time.sleep(max(0, wait_seconds))
                return _ok(action=clean_action, output=f"Pressed {key}.", **_page_state(page))

            if clean_action == "scroll":
                signed_amount = -abs(int(amount)) if direction == "up" else abs(int(amount))
                page.mouse.wheel(0, signed_amount * 240)
                time.sleep(max(0, wait_seconds))
                return _ok(action=clean_action, output=f"Scrolled {direction}.", **_page_state(page))

            if clean_action == "screenshot":
                path = _save_screenshot(page, screenshot_path)
                return _ok(action=clean_action, output=f"Saved browser screenshot: {path}", path=path, **_page_state(page))

            return _fail(f"Unknown browser_agent action: {clean_action}", action=clean_action)
        except Exception as e:
            return _fail(str(e), action=clean_action)


def send_whatsapp_via_brave(
    phone: str = "",
    message_text: str = "",
    receiver: str = "",
    auto_send: bool = True,
    timeout_seconds: float = 45,
) -> dict[str, Any]:
    clean_message = message_text.strip()

    if not clean_message:
        return _fail("message_text is required.", platform="whatsapp", sent=False)
    if not phone and not receiver:
        return _fail("phone or receiver contact name is required.", platform="whatsapp", sent=False)

    with _LOCK:
        try:
            page = _ensure_page(timeout_seconds=timeout_seconds)
            page = _whatsapp_prefer_existing_page(page, timeout_seconds)
            web_url, clean_phone = _whatsapp_open_chat(page, phone, receiver, timeout_seconds, text=clean_message)

            # WhatsApp Web can spend a few seconds booting even with a saved session.
            for _ in range(12):
                text = _visible_text(page, max_chars=5000)
                if _whatsapp_login_required(text) or _whatsapp_invalid_number(text):
                    break
                send_locator, _ = _first_visible_locator(
                    page,
                    WHATSAPP_SEND_SELECTORS,
                )
                if send_locator is not None:
                    break
                time.sleep(0.75)

            page_text = _whatsapp_wait_for_app(page, timeout_seconds)

            if _whatsapp_login_required(page_text):
                return _ok(
                    action="whatsapp_send",
                    platform="whatsapp",
                    receiver=receiver,
                    phone=clean_phone,
                    contact_lookup="whatsapp_web" if not clean_phone else "phone_url",
                    status="login_required",
                    sent=False,
                    whatsapp_url=web_url,
                    output=(
                        "Opened WhatsApp Web in Dexter-controlled Brave. "
                        "I waited for manual login, but it was not completed in time. "
                        "Scan the QR code or finish login, then ask Dexter to send the message again."
                    ),
                    **_page_state(page),
                )

            if _whatsapp_invalid_number(page_text):
                return _fail(
                    "WhatsApp Web says this phone number is invalid.",
                    action="whatsapp_send",
                    platform="whatsapp",
                    receiver=receiver,
                    phone=clean_phone,
                    sent=False,
                    url=web_url,
                )

            if not clean_phone:
                message_box, _ = _first_visible_locator(page, WHATSAPP_MESSAGE_BOX_SELECTORS)
                if message_box is None:
                    return _fail(
                        f"Could not open a WhatsApp chat named {receiver}.",
                        action="whatsapp_send",
                        platform="whatsapp",
                        receiver=receiver,
                        sent=False,
                        url=web_url,
                    )
                _whatsapp_type_into(message_box, page, clean_message, timeout_seconds)
                time.sleep(0.4)

            if not auto_send:
                return _ok(
                    action="whatsapp_send",
                    platform="whatsapp",
                    receiver=receiver,
                    phone=clean_phone,
                    contact_lookup="whatsapp_web" if not clean_phone else "phone_url",
                    status="drafted",
                    sent=False,
                    whatsapp_url=web_url,
                    output=f"Opened WhatsApp Web draft for {receiver or clean_phone}. Review it and press Send.",
                    **_page_state(page),
                )

            clicked_selector = ""
            send_locator, clicked_selector = _first_visible_locator(
                page,
                WHATSAPP_SEND_SELECTORS,
            )

            if send_locator is not None:
                send_locator.click(timeout=_timeout_ms(timeout_seconds))
            else:
                page.keyboard.press("Enter")
                clicked_selector = "keyboard Enter"

            time.sleep(1.2)
            return _ok(
                action="whatsapp_send",
                platform="whatsapp",
                receiver=receiver,
                phone=clean_phone,
                contact_lookup="whatsapp_web" if not clean_phone else "phone_url",
                status="attempted_send",
                sent=True,
                delivery_verified=False,
                whatsapp_url=web_url,
                clicked=clicked_selector,
                output=(
                    f"Used Brave WhatsApp Web and attempted to send the message to {receiver or clean_phone}. "
                    "Delivery cannot be verified from the local browser automation yet."
                ),
                **_page_state(page),
            )
        except Exception as e:
            return _fail(
                str(e),
                action="whatsapp_send",
                platform="whatsapp",
                receiver=receiver,
                phone=_whatsapp_phone(phone) or _whatsapp_phone(receiver),
                sent=False,
                url=locals().get("web_url", "https://web.whatsapp.com"),
            )


def send_whatsapp_file_via_brave(
    phone: str = "",
    file_path: str = "",
    caption: str = "",
    receiver: str = "",
    auto_send: bool = True,
    timeout_seconds: float = 75,
) -> dict[str, Any]:
    clean_caption = caption.strip()

    if not phone and not receiver:
        return _fail("phone or receiver contact name is required.", platform="whatsapp", sent=False)

    try:
        target_file = resolve_safe_path(file_path)
    except Exception as e:
        return _fail(str(e), platform="whatsapp", sent=False, file_path=file_path)

    if not target_file.exists() or not target_file.is_file():
        return _fail("File not found.", platform="whatsapp", sent=False, file_path=str(target_file))

    with _LOCK:
        try:
            page = _ensure_page(timeout_seconds=timeout_seconds)
            page = _whatsapp_prefer_existing_page(page, timeout_seconds)
            web_url, clean_phone = _whatsapp_open_chat(page, phone, receiver, timeout_seconds)

            page_text = _whatsapp_wait_for_app(page, timeout_seconds)

            if _whatsapp_login_required(page_text):
                return _ok(
                    action="whatsapp_file_send",
                    platform="whatsapp",
                    receiver=receiver,
                    phone=clean_phone,
                    file_path=str(target_file),
                    contact_lookup="whatsapp_web" if not clean_phone else "phone_url",
                    status="login_required",
                    sent=False,
                    whatsapp_url=web_url,
                    output=(
                        "Opened WhatsApp Web in Dexter-controlled Brave. "
                        "I waited for manual login, but it was not completed in time. "
                        "Scan the QR code or finish login, then ask Dexter to send the file again."
                    ),
                    **_page_state(page),
                )

            if _whatsapp_invalid_number(page_text):
                return _fail(
                    "WhatsApp Web says this phone number is invalid.",
                    action="whatsapp_file_send",
                    platform="whatsapp",
                    receiver=receiver,
                    phone=clean_phone,
                    sent=False,
                    url=web_url,
                    file_path=str(target_file),
                )

            attached_via = _whatsapp_attach_document_file(page, target_file, timeout_seconds)
            time.sleep(1.2)
            page_text = _visible_text(page, max_chars=6000)
            if _whatsapp_file_attachment_rejected(page_text):
                return _fail(
                    "WhatsApp rejected the attachment as unsupported.",
                    action="whatsapp_file_send",
                    platform="whatsapp",
                    receiver=receiver,
                    phone=clean_phone,
                    sent=False,
                    url=web_url,
                    file_path=str(target_file),
                    text=page_text,
                )

            if clean_caption:
                caption_locator, _ = _first_visible_locator(
                    page,
                    WHATSAPP_CAPTION_SELECTORS,
                )
                if caption_locator is not None:
                    try:
                        caption_locator.click(timeout=_timeout_ms(5), force=True)
                        page.keyboard.insert_text(clean_caption)
                    except Exception:
                        pass

            if not auto_send:
                return _ok(
                    action="whatsapp_file_send",
                    platform="whatsapp",
                    receiver=receiver,
                    phone=clean_phone,
                    file_path=str(target_file),
                    caption=clean_caption,
                    contact_lookup="whatsapp_web" if not clean_phone else "phone_url",
                    status="drafted",
                    sent=False,
                    whatsapp_url=web_url,
                    attached_via=attached_via,
                    output=f"Attached {target_file.name} in WhatsApp Web for {receiver or clean_phone}. Review it and press Send.",
                    **_page_state(page),
                )

            send_locator, clicked_selector = _first_visible_locator(
                page,
                WHATSAPP_SEND_SELECTORS,
            )
            if send_locator is not None:
                send_locator.click(timeout=_timeout_ms(timeout_seconds))
            else:
                page.keyboard.press("Enter")
                clicked_selector = "keyboard Enter"

            time.sleep(1.5)
            return _ok(
                action="whatsapp_file_send",
                platform="whatsapp",
                receiver=receiver,
                phone=clean_phone,
                file_path=str(target_file),
                caption=clean_caption,
                contact_lookup="whatsapp_web" if not clean_phone else "phone_url",
                status="attempted_send",
                sent=True,
                delivery_verified=False,
                whatsapp_url=web_url,
                clicked=clicked_selector,
                attached_via=attached_via,
                output=(
                    f"Used Brave WhatsApp Web and attempted to send {target_file.name} to {receiver or clean_phone}. "
                    "Delivery cannot be verified from the local browser automation yet."
                ),
                **_page_state(page),
            )
        except Exception as e:
            return _fail(
                str(e),
                action="whatsapp_file_send",
                platform="whatsapp",
                receiver=receiver,
                phone=_whatsapp_phone(phone) or _whatsapp_phone(receiver),
                sent=False,
                url=locals().get("web_url", "https://web.whatsapp.com"),
                file_path=str(target_file),
            )


def close_browser_agent() -> None:
    global _PLAYWRIGHT, _BROWSER, _CONTEXT, _PAGE, _OWNER_THREAD_ID

    if _OWNER_THREAD_ID is not None and _OWNER_THREAD_ID != _current_thread_id():
        _discard_browser_handles()
        return

    try:
        if _CONTEXT is not None and _BROWSER is None:
            _CONTEXT.close()
    finally:
        _CONTEXT = None
        _PAGE = None

    try:
        if _BROWSER is not None:
            disconnect = getattr(_BROWSER, "disconnect", None)
            if callable(disconnect):
                disconnect()
    finally:
        _BROWSER = None

    try:
        if _PLAYWRIGHT is not None:
            _PLAYWRIGHT.stop()
    finally:
        _PLAYWRIGHT = None
        _OWNER_THREAD_ID = None


_browser_agent_impl = browser_agent
_send_whatsapp_via_brave_impl = send_whatsapp_via_brave
_send_whatsapp_file_via_brave_impl = send_whatsapp_file_via_brave
_close_browser_agent_impl = close_browser_agent


def browser_agent(
    action: str = "status",
    url: str = "",
    query: str = "",
    text: str = "",
    selector: str = "",
    button_text: str = "",
    key: str = "Enter",
    direction: str = "down",
    amount: int = 5,
    wait_seconds: float = 0.5,
    timeout_seconds: float = 20,
    screenshot_path: str = "",
) -> dict[str, Any]:
    return run_on_browser_thread(
        _browser_agent_impl,
        action=action,
        url=url,
        query=query,
        text=text,
        selector=selector,
        button_text=button_text,
        key=key,
        direction=direction,
        amount=amount,
        wait_seconds=wait_seconds,
        timeout_seconds=timeout_seconds,
        screenshot_path=screenshot_path,
    )


def send_whatsapp_via_brave(
    phone: str = "",
    message_text: str = "",
    receiver: str = "",
    auto_send: bool = True,
    timeout_seconds: float = 45,
) -> dict[str, Any]:
    return run_on_browser_thread(
        _send_whatsapp_via_brave_impl,
        phone=phone,
        message_text=message_text,
        receiver=receiver,
        auto_send=auto_send,
        timeout_seconds=timeout_seconds,
    )


def send_whatsapp_file_via_brave(
    phone: str = "",
    file_path: str = "",
    caption: str = "",
    receiver: str = "",
    auto_send: bool = True,
    timeout_seconds: float = 75,
) -> dict[str, Any]:
    return run_on_browser_thread(
        _send_whatsapp_file_via_brave_impl,
        phone=phone,
        file_path=file_path,
        caption=caption,
        receiver=receiver,
        auto_send=auto_send,
        timeout_seconds=timeout_seconds,
    )


def close_browser_agent() -> None:
    return run_on_browser_thread(_close_browser_agent_impl)
