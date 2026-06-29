from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _detect_user_home() -> Path:
    override = os.getenv("DEXTER_USER_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    for parent in [PROJECT_ROOT, *PROJECT_ROOT.parents]:
        if parent.parent.name == "Users":
            return parent.resolve()

    return Path.home().resolve()


USER_HOME = _detect_user_home()

SAFE_ROOT_ALIASES: dict[str, Path] = {
    ".": PROJECT_ROOT,
    "project": PROJECT_ROOT,
    "workspace": PROJECT_ROOT,
    "dexter": PROJECT_ROOT,
    "home": USER_HOME,
    "~": USER_HOME,
    "desktop": USER_HOME / "Desktop",
    "downloads": USER_HOME / "Downloads",
    "documents": USER_HOME / "Documents",
    "pictures": USER_HOME / "Pictures",
    "movies": USER_HOME / "Movies",
    "videos": USER_HOME / "Movies",
    "music": USER_HOME / "Music",
    "career": USER_HOME / "Career",
    "personal": USER_HOME / "Personal",
    "obsidian": USER_HOME / "Obsidian",
}

SKIP_PATH_PARTS = {
    ".cache",
    ".codex",
    ".git",
    ".next",
    ".npm",
    ".ollama",
    ".venv",
    "__pycache__",
    "cache",
    "caches",
    "library",
    "node_modules",
    "qdrant_storage",
    "site-packages",
    "venv",
}

TEXT_EXTENSIONS = {
    "",
    ".cfg",
    ".conf",
    ".csv",
    ".css",
    ".env",
    ".html",
    ".ini",
    ".ipynb",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".log",
    ".md",
    ".py",
    ".rb",
    ".rst",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


def safe_roots() -> list[Path]:
    roots = list(SAFE_ROOT_ALIASES.values())

    for item in os.getenv("DEXTER_SAFE_FILE_ROOTS", "").split(","):
        clean = item.strip()
        if clean:
            roots.append(Path(clean).expanduser())

    resolved: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            path = root.resolve()
        except Exception:
            continue
        key = str(path)
        if key not in seen:
            resolved.append(path)
            seen.add(key)

    return resolved


def _expand_user_path(raw: str) -> Path:
    if raw == "~":
        return USER_HOME
    if raw.startswith("~/"):
        return USER_HOME / raw[2:]
    return Path(raw).expanduser()


def resolve_safe_path(path: str = "", name: str = "") -> Path:
    raw = (path or "project").strip()
    lower = raw.lower()
    if "/" in lower:
        alias, remainder = raw.split("/", 1)
        base_alias = SAFE_ROOT_ALIASES.get(alias.lower())
        base = base_alias / remainder if base_alias else _expand_user_path(raw)
    else:
        base = SAFE_ROOT_ALIASES.get(lower, _expand_user_path(raw))
    target = base / name if name else base
    resolved = target.resolve()

    for root in safe_roots():
        try:
            if resolved == root or resolved.is_relative_to(root):
                return resolved
        except Exception:
            continue

    raise ValueError(f"Access denied outside safe roots: {resolved}")


def display_path(path: Path) -> str:
    resolved = path.resolve()

    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        pass

    try:
        home_relative = resolved.relative_to(USER_HOME)
        if str(home_relative) == ".":
            return "~"
        return "~/" + str(home_relative)
    except ValueError:
        return str(resolved)


def should_skip_path(path: Path) -> bool:
    for part in path.parts:
        lower = part.lower()
        if lower in SKIP_PATH_PARTS:
            return True
        if lower.endswith((".app", ".photoslibrary")):
            return True
        if part.startswith(".") and part not in {".env.example"}:
            return True

    return False


def is_text_file(path: Path, max_bytes: int) -> bool:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return False

    try:
        return path.stat().st_size <= max_bytes
    except OSError:
        return False
