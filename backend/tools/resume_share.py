from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.tools.document_store import latest_resume_documents
from backend.tools.safe_paths import PROJECT_ROOT, USER_HOME, display_path, resolve_safe_path, should_skip_path
from backend.utils.logger import log_action


RESUME_EXTENSIONS = {".pdf", ".doc", ".docx", ".rtf", ".tex"}
MAX_SCAN_FILES = 40000


def _ok(**payload: Any) -> dict[str, Any]:
    result = {"ok": True, "tool": "send_resume_whatsapp", **payload}
    log_action("send_resume_whatsapp", result)
    return result


def _fail(error: str, **payload: Any) -> dict[str, Any]:
    result = {"ok": False, "tool": "send_resume_whatsapp", "error": error, **payload}
    log_action("send_resume_whatsapp_error", result)
    return result


def _candidate_record(path: Path, source: str, score: float = 0) -> dict[str, Any]:
    stat = path.stat()
    lower = str(path).lower()
    name = path.name.lower()

    if "resume" in name:
        score += 100
    if re.search(r"\bcv\b", name):
        score += 55
    if "vishal" in name:
        score += 20
    if path.suffix.lower() == ".pdf":
        score += 35
    elif path.suffix.lower() == ".docx":
        score += 20
    elif path.suffix.lower() in {".doc", ".rtf"}:
        score += 12
    elif path.suffix.lower() == ".tex":
        score += 5
    if any(part in lower for part in ("/desktop/", "/documents/", "/downloads/", "/career/", "/data/user_documents/")):
        score += 12
    if any(word in lower for word in ("old", "archive", "backup", "template", "sample", "cover letter")):
        score -= 30

    return {
        "path": display_path(path),
        "absolute_path": str(path.resolve()),
        "name": path.name,
        "extension": path.suffix.lower(),
        "source": source,
        "score": round(score, 2),
        "size_bytes": stat.st_size,
        "modified_at": stat.st_mtime,
    }


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in candidates:
        key = item["absolute_path"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def find_resume_candidates(query: str = "resume", root: str = "home", max_candidates: int = 8) -> list[dict[str, Any]]:
    clean_query = (query or "resume").strip().lower()
    query_terms = [term for term in re.split(r"\W+", clean_query) if term]
    candidates: list[dict[str, Any]] = []

    for doc in latest_resume_documents(limit=5):
        raw_path = str(doc.get("path") or "")
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        try:
            resolved = path.resolve()
        except Exception:
            continue
        if resolved.exists() and resolved.is_file() and resolved.suffix.lower() in RESUME_EXTENSIONS:
            candidates.append(_candidate_record(resolved, source="uploaded_document", score=500))

    try:
        requested_root = resolve_safe_path(root or "home")
    except Exception:
        requested_root = USER_HOME

    roots: list[Path]
    if requested_root == USER_HOME:
        roots = [
            PROJECT_ROOT / "data" / "user_documents",
            USER_HOME / "Desktop",
            USER_HOME / "Documents",
            USER_HOME / "Downloads",
            USER_HOME / "Career",
            USER_HOME / "Obsidian",
        ]
    else:
        roots = [requested_root]

    scanned = 0
    for search_root in roots:
        if not search_root.exists():
            continue
        for path in search_root.rglob("*"):
            if scanned >= MAX_SCAN_FILES:
                break
            if should_skip_path(path):
                continue
            if not path.is_file():
                continue
            scanned += 1
            if path.suffix.lower() not in RESUME_EXTENSIONS:
                continue

            lower_path = str(path).lower()
            lower_name = path.name.lower()
            looks_like_resume = "resume" in lower_name or re.search(r"\bcv\b", lower_name)
            query_match = any(term in lower_path for term in query_terms)
            if not looks_like_resume and not query_match:
                continue

            candidates.append(_candidate_record(path.resolve(), source="local_search"))

    candidates = _dedupe_candidates(candidates)
    candidates.sort(key=lambda item: (item["score"], item["modified_at"]), reverse=True)
    return candidates[: max(1, int(max_candidates or 8))]


def send_resume_whatsapp(
    receiver: str,
    query: str = "resume",
    file_path: str = "",
    caption: str = "Here is my resume.",
    root: str = "home",
    auto_send: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    clean_receiver = (receiver or "").strip()
    clean_caption = (caption or "Here is my resume.").strip()

    if not clean_receiver:
        return _fail("receiver is required.")

    if file_path:
        try:
            resume_path = resolve_safe_path(file_path)
        except Exception as e:
            return _fail(str(e), receiver=clean_receiver, file_path=file_path)
        if not resume_path.exists() or not resume_path.is_file():
            return _fail("Resume file not found.", receiver=clean_receiver, file_path=str(resume_path))
        selected = _candidate_record(resume_path, source="explicit_file", score=1000)
        candidates = [selected]
    else:
        candidates = find_resume_candidates(query=query, root=root)
        if not candidates:
            return _fail(
                "Could not find a local resume file.",
                receiver=clean_receiver,
                query=query,
                candidates=[],
                output="I could not find a local resume. Upload it to Dexter or give me the file path, then try again.",
            )
        selected = candidates[0]
        resume_path = Path(selected["absolute_path"])

    if dry_run:
        return _ok(
            action="dry_run",
            receiver=clean_receiver,
            selected_resume=selected,
            candidates=candidates,
            status="dry_run",
            sent=False,
            output=f"Dry run: would send {selected['name']} to {clean_receiver} through WhatsApp.",
        )

    from backend.tools.browser_agent import send_whatsapp_file_via_brave

    result = send_whatsapp_file_via_brave(
        phone="",
        file_path=str(resume_path),
        caption=clean_caption,
        receiver=clean_receiver,
        auto_send=auto_send,
    )
    result["tool"] = "send_resume_whatsapp"
    result["selected_resume"] = selected
    result["candidates"] = candidates
    return result
