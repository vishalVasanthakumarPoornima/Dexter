from pathlib import Path
from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel

from backend.agents.core_agent import run_agent
from backend.models.ollama_client import llm_status
from backend.permissions import policy
from backend.tools.document_store import list_documents, save_uploaded_document
from backend.tools.filesystem import read_file, search_files
from backend.tools.registry import list_tools
from backend.tools.speech_to_text import transcribe_audio
from backend.tools.terminal import list_allowed_commands, run_command
from backend.tools.tool_audit import audit_tools
from backend.api.jobs import router as jobs_router

router = APIRouter()
router.include_router(jobs_router)


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
def chat(req: ChatRequest):
    response = run_agent(req.message)
    return {"response": response}


@router.get("/status")
def status():
    log_path = Path("logs/audit_log.jsonl")
    return {
        "backend": "online",
        "dexter_core": "online",
        "memory": "active",
        "tools_count": len(list_tools()),
        "logs_exist": log_path.exists(),
    }


@router.get("/llm/status")
def get_llm_status():
    return llm_status()


@router.get("/tools/list")
def tools_list():
    return {"tools": list_tools()}


@router.get("/tools/allowed-commands")
def tools_allowed_commands():
    return {"commands": list_allowed_commands()}


@router.get("/tools/read-file")
def tools_read_file(path: str = Query(...)):
    return read_file(path)


@router.get("/tools/search")
def tools_search(query: str = Query(...), root: str = ".", max_results: int = 75):
    return search_files(query=query, root=root, max_results=max_results)


@router.get("/tools/audit")
def tools_audit(include_side_effects: bool = False):
    return audit_tools(include_side_effects=include_side_effects)


@router.get("/tools/terminal")
def tools_terminal(command: str):
    return run_command(command)


@router.get("/logs")
def get_logs():
    log_path = Path("logs/audit_log.jsonl")

    if not log_path.exists():
        return {"logs": []}

    logs = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            logs.append(line.strip())

    return {"logs": logs[-100:]}


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), kind: str = "resume"):
    content = await file.read()
    return save_uploaded_document(
        filename=file.filename or "document",
        content=content,
        content_type=file.content_type or "",
        kind=kind,
    )


@router.get("/documents")
def documents():
    return {"documents": list_documents()}


@router.post("/speech/transcribe")
async def speech_transcribe(file: UploadFile = File(...)):
    return await transcribe_audio(file)


@router.get("/permissions/pending")
def get_pending():
    return {"pending": policy.list_pending()}

@router.post("/permissions/approve")
def approve(cmd: str = Query(...)):
    success = policy.approve_command(cmd)
    return {"approved": success}

@router.post("/permissions/deny")
def deny(cmd: str = Query(...)):
    success = policy.deny_command(cmd)
    return {"denied": success}
