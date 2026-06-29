# Dexter — Local Autonomous AI Assistant

Dexter is a local-first Jarvis-style AI assistant.

## Quick Start

Start the backend and frontend together:

```bash
./start.sh
```

The script reuses running services when possible and writes dev logs to `logs/dev/`.

## Jobs OS

Run the fixture-backed Jobs OS demo:

```bash
python -m backend.app.jobs.cli run-daily --demo
```

Then start Dexter and open the Jobs tab:

```bash
./start.sh
```

Common Jobs OS commands:

```bash
python -m backend.app.jobs.cli ingest --source all
python -m backend.app.jobs.cli score
python -m backend.app.jobs.cli generate-packets
python -m backend.app.jobs.cli report
python -m backend.app.jobs.cli apply-session --job-id <id> --demo
python -m backend.app.jobs.cli health
```

Create your local source/profile config, then add optional keys in `.env`:

```bash
cp config/jobs.example.yaml config/jobs.yaml
```

```bash
USAJOBS_API_KEY=
USAJOBS_EMAIL=
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
CAREERJET_API_KEY=
JOOBLE_API_KEY=
BRAVE_SEARCH_API_KEY=
```

Public no-key sources include Remotive, The Muse, Arbeitnow, GitHub lists, RSS feeds, and configured Greenhouse/Lever/Ashby/SmartRecruiters/Recruitee company feeds.

Jobs OS never auto-submits external applications. Restricted sources such as LinkedIn, Indeed, and Glassdoor are manual-only or supervised-link sources.

## Private Contact Aliases

If macOS Contacts access is blocked, Dexter can resolve names from a private local file at `data/contact_aliases.json`:

```json
{
  "dad": "+15551234567"
}
```

That file is ignored by git.

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

## Hybrid LLM Mode

Dexter can route model calls through local Ollama or OpenRouter:

- `DEXTER_LLM_PROVIDER=auto` keeps normal chat local and uses OpenRouter for online, browser, job, signup, and application-style tasks when an API key is configured.
- `DEXTER_LLM_PROVIDER=local` forces Ollama.
- `DEXTER_LLM_PROVIDER=openrouter` forces OpenRouter and returns an error if no API key is configured.

Set `DEXTER_OPENROUTER_API_KEY` in `.env` to enable the cloud route. `OPENROUTER_API_KEY` is also supported. The default OpenRouter model is `nvidia/nemotron-3-ultra-550b-a55b:free`.

## Browser Control

Dexter can use either a dedicated persistent browser profile or attach to an already-running Chromium browser:

- `DEXTER_BROWSER_CONNECTION=persistent` launches the configured browser with `DEXTER_BROWSER_PROFILE_DIR`. This is the safest default because Dexter owns that profile.
- `DEXTER_BROWSER_CONNECTION=cdp` attaches to an existing browser exposed through `DEXTER_BROWSER_CDP_URL`, usually `http://127.0.0.1:9222`. This can use your signed-in main browser session, but that browser must be started with remote debugging enabled.
- `DEXTER_BROWSER_CDP_RELAUNCH_EXISTING=false` keeps normal Dexter browser actions attach-only. Dexter will fail clearly if CDP is not reachable instead of quitting or relaunching your main browser.
- `DEXTER_BROWSER_CDP_FORCE_QUIT_EXISTING=false` prevents Dexter from force-quitting the browser. Keep this off unless you explicitly ask Dexter to relaunch the existing browser session.

For Brave on macOS:

```bash
open -a "Brave Browser" --args --remote-debugging-port=9222 --restore-last-session
```

You can also ask Dexter to `use the already opened tab` to run its existing-session relaunch action.

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
