import subprocess

# Only allow these commands for now
ALLOWED_COMMANDS = {
    "ls": "List directory contents",
    "pwd": "Print current working directory",
    "whoami": "Current user",
    "git status": "Git repo status",
}

def run_command(command: str) -> dict:
    command = command.strip()

    if command not in ALLOWED_COMMANDS:
        return {"ok": False, "error": "Command not allowed"}

    try:
        result = subprocess.run(
            command, shell=True, check=True, capture_output=True, text=True
        )
        return {"ok": True, "command": command, "output": result.stdout.strip()}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "command": command, "error": e.stderr.strip()}
