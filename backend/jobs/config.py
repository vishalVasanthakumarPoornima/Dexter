from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "jobs.yaml"

DEFAULT_JOBS_CONFIG: dict[str, Any] = {
    "profile": {
        "name": "",
        "email": "",
        "phone": "",
        "location": "",
        "github": "",
        "linkedin": "",
        "portfolio": "",
        "resume_path": "",
        "work_authorization": "",
        "sponsorship_needed": None,
    },
    "targets": {
        "roles": [
            "Software Engineer Intern",
            "AI Engineer Intern",
            "Security Engineer Intern",
            "Backend Engineer Intern",
        ],
        "locations": ["Remote", "Bay Area", "San Jose", "San Francisco", "Fremont"],
        "include_remote": True,
        "include_hybrid": True,
        "include_onsite": True,
        "employment_types": ["internship", "new_grad", "full_time"],
    },
    "limits": {
        "max_jobs_per_source": 100,
        "max_ranked_jobs": 50,
        "max_application_packets_per_run": 10,
        "max_apply_sessions_per_day": 5,
    },
    "safety": {
        "auto_submit": False,
        "require_approval_before_submit": True,
        "restricted_sources_manual_only": True,
        "captcha_bypass": False,
    },
    "sources": {
        "greenhouse": {"enabled": True, "companies": []},
        "lever": {"enabled": True, "companies": []},
        "usajobs": {
            "enabled": False,
            "api_key_env": "USAJOBS_API_KEY",
            "email_env": "USAJOBS_EMAIL",
        },
        "adzuna": {
            "enabled": False,
            "app_id_env": "ADZUNA_APP_ID",
            "app_key_env": "ADZUNA_APP_KEY",
        },
        "remotive": {"enabled": True},
        "ashby": {"enabled": True, "boards": []},
        "smartrecruiters": {"enabled": True, "companies": []},
        "recruitee": {"enabled": True, "companies": []},
        "themuse": {"enabled": True, "categories": []},
        "arbeitnow": {"enabled": True},
        "careerjet": {
            "enabled": False,
            "api_key_env": "CAREERJET_API_KEY",
            "locale_code": "en_US",
        },
        "jooble": {
            "enabled": False,
            "api_key_env": "JOOBLE_API_KEY",
        },
        "brave_search": {
            "enabled": False,
            "api_key_env": "BRAVE_SEARCH_API_KEY",
            "queries": [],
        },
        "github_lists": {
            "enabled": True,
            "repos": ["https://github.com/vanshb03/Summer2027-Internships"],
        },
        "rss": {"enabled": True, "feeds": []},
        "manual_link": {"enabled": True},
        "company_careers": {"enabled": True, "companies": []},
        "web_discovery": {"enabled": True, "queries": []},
        "restricted_manual": {
            "enabled": True,
            "domains": ["linkedin.com", "indeed.com", "glassdoor.com"],
        },
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_jobs_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path or os.getenv("DEXTER_JOBS_CONFIG", DEFAULT_CONFIG_PATH))
    loaded: dict[str, Any] = {}
    if config_path.exists():
        try:
            import yaml

            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                loaded = data
        except Exception:
            loaded = {}

    config = _deep_merge(DEFAULT_JOBS_CONFIG, loaded)
    env_resume = os.getenv("DEXTER_JOBS_RESUME_PATH", "").strip()
    if env_resume:
        config["profile"]["resume_path"] = env_resume
    return config


def jobs_data_dir() -> Path:
    path = PROJECT_ROOT / "data" / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def generated_dir() -> Path:
    path = PROJECT_ROOT / "data" / "generated"
    path.mkdir(parents=True, exist_ok=True)
    return path


def reports_dir() -> Path:
    path = PROJECT_ROOT / "data" / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def raw_payloads_dir() -> Path:
    path = PROJECT_ROOT / "data" / "raw_payloads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def screenshots_dir() -> Path:
    path = PROJECT_ROOT / "data" / "screenshots"
    path.mkdir(parents=True, exist_ok=True)
    return path
