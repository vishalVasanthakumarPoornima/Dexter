import subprocess
import urllib.parse
from backend.utils.logger import log_action


def open_app(app: str) -> dict:
    app = app.strip()
    if not app:
        return {"ok": False, "error": "No app name provided."}

    try:
        completed = subprocess.run(
            ["open", "-a", app],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        result = {"ok": True, "app": app, "output": completed.stdout.strip() or f"Opened {app}"}
        log_action("macos_app_opened", result)
        return result
    except subprocess.CalledProcessError as e:
        result = {"ok": False, "app": app, "error": e.stderr.strip() or f"Could not open {app}"}
        log_action("macos_app_error", result)
        return result


def close_app(app: str) -> dict:
    app = app.strip()
    if not app:
        return {"ok": False, "error": "No app name provided."}

    script = f'tell application "{app}" to quit'

    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        result = {"ok": True, "app": app, "output": f"Closed {app}"}
        log_action("macos_app_closed", result)
        return result
    except subprocess.CalledProcessError as e:
        result = {"ok": False, "app": app, "error": e.stderr.strip() or f"Could not close {app}"}
        log_action("macos_app_close_error", result)
        return result


def list_apps() -> dict:
    try:
        completed = subprocess.run(
            "find /Applications ~/Applications -maxdepth 2 -name '*.app' 2>/dev/null | sed 's#.*/##' | sed 's/.app$//' | sort",
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        apps = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        return {"ok": True, "apps": apps}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def spotify_search(query: str) -> dict:
    clean = query.strip()
    if not clean:
        return {"ok": False, "error": "No Spotify search query provided."}

    encoded = urllib.parse.quote(clean)
    url = f"spotify:search:{encoded}"

    try:
        subprocess.run(["open", url], check=True, capture_output=True, text=True, timeout=10)
        result = {"ok": True, "query": clean, "output": f"Searched Spotify for: {clean}"}
        log_action("spotify_search", result)
        return result
    except subprocess.CalledProcessError as e:
        result = {"ok": False, "query": clean, "error": e.stderr.strip() or "Spotify search failed"}
        log_action("spotify_search_error", result)
        return result


def brave_search(query: str) -> dict:
    import urllib.parse

    clean = query.strip()
    if not clean:
        return {"ok": False, "error": "No search query provided."}

    encoded = urllib.parse.quote_plus(clean)
    url = f"https://www.google.com/search?q={encoded}"

    try:
        completed = subprocess.run(
            ["open", "-a", "Brave Browser", url],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        result = {
            "ok": True,
            "query": clean,
            "output": completed.stdout.strip() or f"Opened Brave search for: {clean}",
        }
        log_action("brave_search", result)
        return result

    except subprocess.CalledProcessError as e:
        result = {
            "ok": False,
            "query": clean,
            "error": e.stderr.strip() or "Brave search failed",
        }
        log_action("brave_search_error", result)
        return result
