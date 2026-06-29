from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a configured Dexter job automation.")
    parser.add_argument("--id", required=True, help="Automation id to run.")
    parser.add_argument("--project-root", default="", help="Dexter project root.")
    args = parser.parse_args()

    project_root = Path(args.project_root or Path(__file__).resolve().parents[1]).resolve()
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))

    from backend.env import load_env

    load_env()

    from backend.tools.job_automation import run_automation_by_id

    result = run_automation_by_id(args.id)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
