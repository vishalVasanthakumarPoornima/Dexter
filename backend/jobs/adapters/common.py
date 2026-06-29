from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

from backend.jobs.config import PROJECT_ROOT


USER_AGENT = "DexterJobsOS/0.1 (+local-personal-agent)"
REQUEST_TIMEOUT = 12
MAX_BODY_BYTES = 3_000_000


def fixture_path(name: str) -> Path:
    return PROJECT_ROOT / "tests" / "fixtures" / "jobs" / name


def load_fixture_json(name: str) -> Any:
    return json.loads(fixture_path(name).read_text(encoding="utf-8"))


def load_fixture_text(name: str) -> str:
    return fixture_path(name).read_text(encoding="utf-8")


def fetch_json(url: str, headers: dict[str, str] | None = None) -> Any:
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
    )
    response.raise_for_status()
    if int(response.headers.get("content-length") or 0) > MAX_BODY_BYTES:
        raise ValueError("Response too large")
    return response.json()


def fetch_text(url: str, headers: dict[str, str] | None = None) -> str:
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
    )
    response.raise_for_status()
    text = response.text
    if len(text.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValueError("Response too large")
    return text


def clean_html(value: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", value or "", flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        parsed = parsedate_to_datetime(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def infer_remote_type(text: str, location: str = "") -> str:
    blob = f"{text} {location}".lower()
    if "remote" in blob:
        return "remote"
    if "hybrid" in blob:
        return "hybrid"
    if location:
        return "onsite"
    return "unknown"


def infer_employment_type(title: str, text: str = "") -> str:
    blob = f"{title} {text}".lower()
    if "intern" in blob:
        return "internship"
    if "new grad" in blob or "university grad" in blob or "entry level" in blob:
        return "new_grad"
    if "part-time" in blob or "part time" in blob:
        return "part_time"
    if "contract" in blob:
        return "contract"
    return "full_time"


def github_raw_url(url: str) -> str:
    clean = url.strip()
    if "github.com" in clean and "/blob/" in clean:
        return clean.replace("https://github.com/", "https://raw.githubusercontent.com/").replace("/blob/", "/")
    if clean.startswith("https://github.com/") and clean.rstrip("/").count("/") == 4:
        return clean.rstrip("/") + "/raw/main/README.md"
    return clean


def first(value: Any, default: str = "") -> str:
    if isinstance(value, list) and value:
        return clean_text(str(value[0]))
    if value is None:
        return default
    return clean_text(str(value))
