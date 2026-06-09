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
