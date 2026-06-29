from pathlib import Path

from backend.tools.safe_paths import (
    PROJECT_ROOT,
    USER_HOME,
    display_path,
    is_text_file,
    resolve_safe_path,
    should_skip_path,
)


def _safe_path(path: str) -> Path:
    raw = (path or "project").strip()
    if raw.startswith(("home/", "~/")):
        return resolve_safe_path(raw)
    if raw.lower() in {
        ".",
        "project",
        "workspace",
        "dexter",
        "home",
        "~",
        "desktop",
        "downloads",
        "documents",
        "career",
        "personal",
        "obsidian",
    }:
        return resolve_safe_path(raw)
    if Path(raw).is_absolute():
        return resolve_safe_path(raw)
    return resolve_safe_path(str(PROJECT_ROOT / raw))


def read_file(path: str) -> dict:
    target = _safe_path(path)

    if not target.exists():
        return {"ok": False, "error": "File not found"}

    if not target.is_file():
        return {"ok": False, "error": "Path is not a file"}

    return {
        "ok": True,
        "path": display_path(target),
        "content": target.read_text(encoding="utf-8", errors="replace"),
    }


def search_files(query: str, root: str = ".", max_results: int = 75) -> dict:
    clean_query = query.strip()
    if not clean_query:
        return {"ok": False, "error": "Search query is required."}

    search_root = _safe_path(root)

    if not search_root.exists():
        return {"ok": False, "error": "Search root not found"}

    matches = []
    scanned = 0
    max_files = 12000 if search_root == USER_HOME else 6000
    max_text_bytes = 700_000
    query_lower = clean_query.lower()

    for path in search_root.rglob("*"):
        if should_skip_path(path):
            continue

        if path.is_file():
            scanned += 1
            relative = display_path(path)

            if query_lower in relative.lower():
                matches.append(relative)
            elif is_text_file(path, max_text_bytes):
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                    if query_lower in content.lower():
                        matches.append(relative)
                except Exception:
                    continue

            if len(matches) >= int(max_results) or scanned >= max_files:
                break

    return {
        "ok": True,
        "query": clean_query,
        "root": display_path(search_root),
        "matches": matches[: int(max_results)],
        "scanned": scanned,
        "truncated": scanned >= max_files or len(matches) >= int(max_results),
    }
