from __future__ import annotations

import re
from pathlib import Path


FIELD_PATTERNS = {
    "email": ("email",),
    "phone": ("phone", "mobile"),
    "location": ("location", "city"),
    "linkedin": ("linkedin",),
    "github": ("github",),
    "portfolio": ("portfolio", "website"),
    "resume": ("resume", "cv"),
    "cover_letter": ("cover",),
    "work_authorization": ("authorization", "work authorized"),
    "sponsorship": ("sponsor", "visa"),
    "name": ("full_name", "full name", "applicant_name"),
}


def analyze_html_form(html: str) -> list[dict]:
    fields = []
    for match in re.finditer(r"<(input|textarea|select)\b([^>]*)>", html, flags=re.I):
        attrs = match.group(2)
        label_blob = attrs.lower()
        name_match = re.search(r'(?:name|id|aria-label|placeholder)=["\']([^"\']+)["\']', attrs, flags=re.I)
        name = name_match.group(1) if name_match else f"field_{len(fields) + 1}"
        kind = "unknown"
        for candidate, tokens in FIELD_PATTERNS.items():
            if any(token in label_blob or token in name.lower() for token in tokens):
                kind = candidate
                break
        fields.append({"name": name, "kind": kind, "raw": match.group(0)})
    return fields


def analyze_form_file(path: str | Path) -> list[dict]:
    return analyze_html_form(Path(path).read_text(encoding="utf-8"))
