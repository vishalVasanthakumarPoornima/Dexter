from __future__ import annotations

from backend.jobs.adapters import ADAPTER_CLASSES
from backend.jobs.adapters.base import JobSourceAdapter
from backend.jobs.config import load_jobs_config


def build_adapters(config: dict | None = None, include_disabled: bool = False) -> dict[str, JobSourceAdapter]:
    cfg = config or load_jobs_config()
    sources = cfg.get("sources", {})
    adapters = {}
    for name, cls in ADAPTER_CLASSES.items():
        source_cfg = sources.get(name, {})
        if not include_disabled and source_cfg.get("enabled", True) is False:
            continue
        adapters[name] = cls(source_cfg)
    return adapters


def source_health(config: dict | None = None) -> list[dict]:
    rows = []
    for name, adapter in build_adapters(config, include_disabled=True).items():
        health = adapter.validate_config()
        rows.append(
            {
                "id": name,
                "name": name,
                "type": getattr(adapter, "source_type", "adapter"),
                "enabled": (config or load_jobs_config()).get("sources", {}).get(name, {}).get("enabled", True),
                "health_status": health.status,
                "message": health.message,
                "requires_api_key": health.requires_api_key,
                "restricted_mode": health.restricted_mode,
            }
        )
    return rows
