import subprocess
from backend.permissions import policy

from backend.utils.logger import log_action

def list_allowed_commands():
    return policy.COMMAND_PERMISSIONS

def run_command(command: str) -> dict:
    command = command.strip()
    level = policy.get_permission_level(command)

    if level == "blocked":
        result = {"ok": False, "command": command, "error": "Command blocked"}
        log_action("terminal_blocked", result)
        return result

    if level in ("sensitive", "sudo"):
        return {"ok": False, "command": command, "error": policy.request_approval(command)}

    try:
        completed = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        result = {"ok": True, "command": command, "output": completed.stdout.strip() or completed.stderr.strip()}
        log_action("terminal_executed", result)
        return result

    except subprocess.TimeoutExpired:
        result = {"ok": False, "command": command, "error": "Command timed out"}
        log_action("terminal_timeout", result)
        return result

    except subprocess.CalledProcessError as e:
        result = {"ok": False, "command": command, "error": e.stderr.strip() or str(e)}
        log_action("terminal_error", result)
        return result
