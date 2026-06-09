# Dexter — Local Autonomous AI Assistant

Dexter is a local-first Jarvis-style AI assistant.

## v0.1 Goal: Dexter Core

Dexter Core will support:

- Local model chat through Ollama
- FastAPI backend
- Tool registry
- File read/search tools
- Approved terminal commands
- Qdrant memory
- Audit logging
- Security-first permissions

## Stack

- Python
- FastAPI
- LangGraph
- Ollama
- Qdrant
- React + Vite later
- Whisper.cpp / Piper / Kokoro later

## Run Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload


Create minimal FastAPI app:

```bash
cat > backend/main.py <<'EOF'
from fastapi import FastAPI
from backend.api.routes import router

app = FastAPI(
    title="Dexter API",
    description="Local-first autonomous AI assistant backend",
    version="0.1.0",
)

app.include_router(router)


@app.get("/")
def root():
    return {"status": "Dexter Core online", "version": "0.1.0"}
