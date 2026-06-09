import json
import os
from datetime import datetime, UTC

LOG_PATH = "logs/audit_log.jsonl"
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)


def log_action(action_type: str, details: dict):
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "action": action_type,
        "details": details,
    }

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
