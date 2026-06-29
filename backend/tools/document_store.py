from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.utils.logger import log_action


DOCUMENTS_DIR = Path("data/user_documents")
INDEX_PATH = DOCUMENTS_DIR / "index.json"
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def _safe_filename(filename: str) -> str:
    name = Path(filename or "document").name
    clean = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return clean or "document"


def _read_index() -> list[dict[str, Any]]:
    if not INDEX_PATH.exists():
        return []

    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    return []


def _write_index(items: list[dict[str, Any]]) -> None:
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _text_preview(path: Path, extension: str) -> str:
    if extension not in {".txt", ".md", ".rtf"}:
        return ""

    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:4000]
    except Exception:
        return ""


def save_uploaded_document(
    filename: str,
    content: bytes,
    content_type: str = "",
    kind: str = "resume",
) -> dict[str, Any]:
    safe_name = _safe_filename(filename)
    extension = Path(safe_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        return {
            "ok": False,
            "error": f"Unsupported document type: {extension or 'unknown'}",
            "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
        }

    if len(content) > MAX_UPLOAD_BYTES:
        return {
            "ok": False,
            "error": "Document is too large.",
            "max_upload_bytes": MAX_UPLOAD_BYTES,
        }

    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stored_name = f"{timestamp}_{safe_name}"
    path = DOCUMENTS_DIR / stored_name
    path.write_bytes(content)

    item = {
        "id": timestamp,
        "original_name": safe_name,
        "stored_name": stored_name,
        "path": str(path),
        "extension": extension,
        "content_type": content_type,
        "kind": kind,
        "size_bytes": len(content),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "text_preview": _text_preview(path, extension),
    }

    items = [item, *_read_index()]
    _write_index(items[:50])
    log_action("document_uploaded", {key: value for key, value in item.items() if key != "text_preview"})

    return {"ok": True, "document": item}


def list_documents() -> list[dict[str, Any]]:
    return _read_index()


def latest_resume_documents(limit: int = 3) -> list[dict[str, Any]]:
    docs = [
        item
        for item in _read_index()
        if item.get("kind") in {"resume", "document", "profile"}
    ]
    return docs[:limit]
