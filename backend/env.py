from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return

    load_dotenv(ENV_PATH, override=False)
