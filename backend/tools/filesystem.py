from pathlib import Path

PROJECT_ROOT = Path.cwd().resolve()


def _safe_path(path: str) -> Path:
    requested = (PROJECT_ROOT / path).resolve()

    if not str(requested).startswith(str(PROJECT_ROOT)):
        raise ValueError("Access denied: path is outside project root")

    return requested


def read_file(path: str) -> dict:
    target = _safe_path(path)

    if not target.exists():
        return {"ok": False, "error": "File not found"}

    if not target.is_file():
        return {"ok": False, "error": "Path is not a file"}

    return {
        "ok": True,
        "path": str(target.relative_to(PROJECT_ROOT)),
        "content": target.read_text(encoding="utf-8", errors="replace"),
    }


def search_files(query: str, root: str = ".") -> dict:
    search_root = _safe_path(root)

    if not search_root.exists():
        return {"ok": False, "error": "Search root not found"}

    matches = []

    for path in search_root.rglob("*"):
        if any(part in {".git", ".venv", "__pycache__", "qdrant_storage"} for part in path.parts):
            continue

        if path.is_file():
            relative = str(path.relative_to(PROJECT_ROOT))

            if query.lower() in relative.lower():
                matches.append(relative)
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                if query.lower() in content.lower():
                    matches.append(relative)
            except Exception:
                continue

    return {"ok": True, "query": query, "matches": matches[:50]}
