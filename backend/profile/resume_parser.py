from __future__ import annotations

from pathlib import Path


def parse_resume_text(path: str) -> str:
    if not path:
        return ""
    target = Path(path).expanduser()
    if not target.exists() or not target.is_file():
        return ""
    suffix = target.suffix.lower()
    if suffix in {".txt", ".md", ".rtf"}:
        return target.read_text(encoding="utf-8", errors="ignore")[:80_000]
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(target))
            return "\n".join(page.extract_text() or "" for page in reader.pages)[:80_000]
        except Exception:
            return ""
    return ""
