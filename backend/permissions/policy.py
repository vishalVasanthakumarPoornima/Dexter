from typing import Literal, Dict, List
from collections import deque
from backend.utils.logger import log_action

# Permission levels
SAFE = "safe"
SENSITIVE = "sensitive"
SUDO = "sudo"
BLOCKED = "blocked"

# Map commands to permission levels
COMMAND_PERMISSIONS: Dict[str, Literal["safe","sensitive","sudo","blocked"]] = {
    "ls": SAFE,
    "ls -la": SAFE,
    "pwd": SAFE,
    "whoami": SAFE,
    "git status": SAFE,
    "git branch": SAFE,
    "git log --oneline -5": SAFE,
    "find . -maxdepth 2 -type f": SAFE,
    "rm -rf": SUDO,
    "mv": SENSITIVE,
    "sudo": SUDO,
}

# Pending sudo approvals
pending_queue: deque = deque()

def get_permission_level(command: str) -> str:
    return COMMAND_PERMISSIONS.get(command.strip(), BLOCKED)

def request_approval(command: str) -> str:
    """Add sudo/sensitive command to pending queue."""
    pending_queue.append(command)
    log_action("permission_requested", {"command": command})
    return f"Approval requested for command: {command}"

def list_pending() -> List[str]:
    return list(pending_queue)

def approve_command(command: str) -> bool:
    if command in pending_queue:
        pending_queue.remove(command)
        log_action("permission_approved", {"command": command})
        return True
    return False

def deny_command(command: str) -> bool:
    if command in pending_queue:
        pending_queue.remove(command)
        log_action("permission_denied", {"command": command})
        return True
    return False
