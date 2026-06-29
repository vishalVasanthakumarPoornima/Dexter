import os
import threading

from backend.env import load_env

load_env()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import router
from backend.models.ollama_client import warmup_model

app = FastAPI(
    title="Dexter API",
    description="Local-first autonomous AI assistant backend",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


def _warm_ollama_background() -> None:
    warmup_model()


@app.on_event("startup")
def startup_tasks():
    if os.getenv("DEXTER_WARMUP_ON_STARTUP", "false").lower() in {"1", "true", "yes"}:
        threading.Thread(target=_warm_ollama_background, daemon=True).start()


@app.get("/")
def root():
    return {"status": "Dexter Core online", "version": "0.1.0"}


@app.post("/llm/warmup")
def llm_warmup():
    return warmup_model()
