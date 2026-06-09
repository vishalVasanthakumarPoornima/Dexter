from pathlib import Path
from fastapi import APIRouter, Query
from pydantic import BaseModel
from backend.tools.registry import list_tools
from backend.tools.filesystem import read_file, search_files
from backend.agents.core_agent import run_agent

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
def chat(req: ChatRequest):
    response = run_agent(req.message)
    return {"response": response}


@router.get("/tools/list")
def tools_list():
    return {"tools": list_tools()}


@router.get("/tools/read-file")
def tools_read_file(path: str = Query(...)):
    return read_file(path)


@router.get("/tools/search")
def tools_search(query: str = Query(...), root: str = "."):
    return search_files(query=query, root=root)


@router.get("/logs")
def get_logs():
    log_path = Path("logs/audit_log.jsonl")

    if not log_path.exists():
        return {"logs": []}

    logs = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            logs.append(line.strip())

    return {"logs": logs}


@router.get("/health")
def health():
    return {"status": "ok"}

from backend.tools.terminal import run_command

@router.get("/tools/terminal")
def tools_terminal(command: str):
    return run_command(command)
