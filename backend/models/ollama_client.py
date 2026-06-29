import json
import os
import time
from typing import Any

import requests

from backend.models import openrouter_client

OLLAMA_BASE_URL = os.getenv("DEXTER_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_URL = os.getenv("DEXTER_OLLAMA_URL", f"{OLLAMA_BASE_URL}/api/chat")
DEFAULT_MODEL = os.getenv("DEXTER_OLLAMA_MODEL", "dolphin-llama3:latest")
DEFAULT_PLANNER_MODEL = os.getenv("DEXTER_PLANNER_MODEL", DEFAULT_MODEL)
DEFAULT_KEEP_ALIVE = os.getenv("DEXTER_OLLAMA_KEEP_ALIVE", "30s")

LOCAL_PROVIDER_NAMES = {"local", "ollama", "dolphin"}
CLOUD_PROVIDER_NAMES = {"cloud", "openrouter"}

CLOUD_TASK_KEYWORDS = {
    "apply",
    "application",
    "applications",
    "browser",
    "current",
    "dice",
    "form",
    "glassdoor",
    "greenhouse",
    "internet",
    "internship",
    "job",
    "jobs",
    "latest",
    "lever",
    "linkedin",
    "login",
    "online",
    "portal",
    "search",
    "signup",
    "simplify",
    "submit",
    "upload",
    "web",
    "website",
}


def _strip_thinking(text: str) -> str:
    if "</think>" in text:
        return text.split("</think>", 1)[1].strip()
    return text.strip()


def _provider_mode() -> str:
    return os.getenv("DEXTER_LLM_PROVIDER", "auto").strip().lower()


def _message_text(messages: list[dict[str, str]]) -> str:
    return "\n".join(str(message.get("content", "")) for message in messages)


def _uses_cloud_keywords(text: str) -> bool:
    lower = text.lower()
    return any(keyword in lower for keyword in CLOUD_TASK_KEYWORDS)


def _looks_like_openrouter_model(model: str) -> bool:
    return "/" in model or model.startswith("openrouter/")


def _openrouter_model_for(model: str) -> str:
    if model and _looks_like_openrouter_model(model):
        return model
    return openrouter_client.DEFAULT_OPENROUTER_MODEL


def _selected_provider(messages: list[dict[str, str]], purpose: str = "chat") -> str:
    mode = _provider_mode()

    if mode in LOCAL_PROVIDER_NAMES:
        return "ollama"

    if mode in CLOUD_PROVIDER_NAMES:
        return "openrouter" if openrouter_client.is_configured() else "openrouter_missing_key"

    if not openrouter_client.is_configured():
        return "ollama"

    text = _message_text(messages)
    if purpose in {"planner", "summary"} and _uses_cloud_keywords(text):
        return "openrouter"

    if purpose == "chat" and _uses_cloud_keywords(text):
        return "openrouter"

    return "ollama"


def _is_forced_cloud() -> bool:
    return _provider_mode() in CLOUD_PROVIDER_NAMES


def ollama_chat_completion(
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    timeout: int = 120,
    options: dict[str, Any] | None = None,
    response_format: str | None = None,
    keep_alive: str | None = DEFAULT_KEEP_ALIVE,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": options or {},
    }

    if keep_alive:
        payload["keep_alive"] = keep_alive

    if response_format:
        payload["format"] = response_format

    response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return _strip_thinking(data.get("message", {}).get("content", ""))


def chat_completion(
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    timeout: int = 120,
    options: dict[str, Any] | None = None,
    response_format: str | None = None,
    keep_alive: str | None = DEFAULT_KEEP_ALIVE,
    purpose: str = "chat",
) -> str:
    provider = _selected_provider(messages, purpose=purpose)

    if provider == "openrouter_missing_key":
        raise RuntimeError(
            "DEXTER_LLM_PROVIDER is set to OpenRouter/cloud, but no OpenRouter API key is configured."
        )

    if provider == "openrouter":
        try:
            return openrouter_client.chat_completion(
                messages=messages,
                model=_openrouter_model_for(model),
                timeout=timeout,
                options=options,
                response_format=response_format,
            )
        except Exception:
            if _is_forced_cloud():
                raise

    return ollama_chat_completion(
        messages=messages,
        model=model,
        timeout=timeout,
        options=options,
        response_format=response_format,
        keep_alive=keep_alive,
    )


def chat_json_completion(
    messages: list[dict[str, str]],
    model: str = DEFAULT_PLANNER_MODEL,
    timeout: int = 45,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    last_text = ""
    last_error: Exception | None = None
    active_messages = messages

    for attempt in range(2):
        try:
            text = chat_completion(
                messages=active_messages,
                model=model,
                timeout=timeout,
                options=options,
                response_format="json",
                purpose="planner",
            )
            last_text = text

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                start = text.find("{")
                end = text.rfind("}")
                if start >= 0 and end > start:
                    return json.loads(text[start : end + 1])
                raise
        except Exception as e:
            last_error = e
            if attempt == 1:
                break
            active_messages = [
                *messages,
                {
                    "role": "assistant",
                    "content": last_text[:1000] if last_text else f"Invalid JSON response: {e}",
                },
                {
                    "role": "user",
                    "content": (
                        "Return exactly one valid JSON object for the next action. "
                        "Do not include markdown, prose, code fences, or any text outside the JSON object."
                    ),
                },
            ]
            time.sleep(0.5)

    snippet = (last_text or str(last_error or "")).strip().replace("\n", " ")[:240]
    raise ValueError(f"LLM did not return valid JSON for tool planning. Response/error: {snippet}")


def chat_with_ollama(
    user_message: str,
    memory_context: str = "",
    model: str = DEFAULT_MODEL,
) -> str:
    system_prompt = """
You are Dexter, Vishal's local autonomous AI assistant.

Answer directly. Do not show chain-of-thought, hidden reasoning, or internal deliberation.
Do not write "Thinking".
Be concise, practical, and useful.
Never claim you created accounts, logged in, applied to jobs, submitted forms, saved passwords, opened apps, or used external websites unless a tool result in the current turn explicitly confirms it.
"""

    if memory_context:
        system_prompt += f"\nRelevant memory:\n{memory_context[:800]}\n"

    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_message},
    ]

    try:
        text = chat_completion(
            messages=messages,
            model=model,
            timeout=300,
            options={
                "temperature": 0.2,
                "num_ctx": 2048,
                "num_predict": int(os.getenv("DEXTER_CHAT_NUM_PREDICT", "160")),
            },
        )

        return text or "No text returned by LLM."

    except Exception as e:
        return f"LLM error: {e}"


def summarize_tool_results(
    user_message: str,
    execution_result: dict[str, Any],
    memory_context: str = "",
    model: str = DEFAULT_MODEL,
) -> str:
    system_prompt = """
You are Dexter, Vishal's local autonomous AI assistant.

Use the tool execution results to answer the user's request directly.
Keep the response concise unless the user explicitly asked for a draft or detailed output.
Mention failures plainly. Do not invent facts beyond the provided tool results.
For messaging tools, only say a message was sent when the tool status is "sent" or "attempted_send"; otherwise say it was drafted, opened, skipped, or failed exactly as reported.
Do not expose hidden reasoning or implementation details.
"""

    if memory_context:
        system_prompt += f"\nRelevant memory:\n{memory_context[:800]}\n"

    tool_payload = json.dumps(execution_result, ensure_ascii=True, indent=2)[:6000]

    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {
            "role": "user",
            "content": (
                f"User request:\n{user_message}\n\n"
                f"Tool execution JSON:\n{tool_payload}\n\n"
                "Now produce Dexter's final response."
            ),
        },
    ]

    try:
        text = chat_completion(
            messages=messages,
            model=model,
            timeout=180,
            options={
                "temperature": 0.25,
                "num_ctx": 4096,
                "num_predict": int(os.getenv("DEXTER_SUMMARY_NUM_PREDICT", "220")),
            },
            purpose="summary",
        )
        return text or "Done."
    except Exception as e:
        return f"LLM error: {e}"


def warmup_model(model: str = DEFAULT_MODEL, system_prompt: str | None = None) -> dict[str, Any]:
    messages: list[dict[str, str]] = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": "hi"})

    try:
        text = chat_completion(
            messages=messages,
            model=model,
            timeout=int(os.getenv("DEXTER_WARMUP_TIMEOUT", "90")),
            options={
                "temperature": 0,
                "num_ctx": 1024,
                "num_predict": 1,
            },
        )
        return {"ok": True, "model": model, "response": text}
    except Exception as e:
        return {"ok": False, "model": model, "error": str(e)}


def llm_status() -> dict[str, Any]:
    sample_online_task = [
        {"role": "user", "content": "apply for the latest SWE jobs online"}
    ]
    sample_local_task = [{"role": "user", "content": "hello dexter"}]

    return {
        "provider_mode": _provider_mode() or "auto",
        "local": {
            "provider": "ollama",
            "model": DEFAULT_MODEL,
            "base_url": OLLAMA_BASE_URL,
        },
        "cloud": {
            "provider": "openrouter",
            **openrouter_client.status(),
        },
        "routing": {
            "local_chat": _selected_provider(sample_local_task, purpose="chat"),
            "online_tasks": _selected_provider(sample_online_task, purpose="planner"),
            "auto_cloud_keywords": sorted(CLOUD_TASK_KEYWORDS),
        },
    }
