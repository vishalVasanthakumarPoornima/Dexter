from __future__ import annotations

import os
from typing import Any

import requests


OPENROUTER_BASE_URL = os.getenv(
    "DEXTER_OPENROUTER_BASE_URL",
    "https://openrouter.ai/api/v1",
).rstrip("/")
OPENROUTER_CHAT_URL = f"{OPENROUTER_BASE_URL}/chat/completions"
DEFAULT_OPENROUTER_MODEL = os.getenv(
    "DEXTER_OPENROUTER_MODEL",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
)


def get_api_key() -> str:
    return (
        os.getenv("DEXTER_OPENROUTER_API_KEY", "").strip()
        or os.getenv("OPENROUTER_API_KEY", "").strip()
    )


def is_configured() -> bool:
    return bool(get_api_key())


def _extract_output_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""

    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = message.get("content", "")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                chunks.append(item["text"])
        return "\n".join(chunk.strip() for chunk in chunks if chunk.strip()).strip()

    return ""


def _max_tokens(options: dict[str, Any] | None) -> int | None:
    configured = os.getenv("DEXTER_OPENROUTER_MAX_TOKENS", "").strip()
    if configured:
        return int(configured)

    if not options:
        return None

    if options.get("max_tokens"):
        return int(options["max_tokens"])

    if options.get("max_output_tokens"):
        return int(options["max_output_tokens"])

    if options.get("num_predict"):
        return int(options["num_predict"])

    return None


def _temperature(options: dict[str, Any] | None) -> float | None:
    configured = os.getenv("DEXTER_OPENROUTER_TEMPERATURE", "").strip()
    if configured:
        return float(configured)

    if options and options.get("temperature") is not None:
        return float(options["temperature"])

    return None


def _headers(api_key: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    referer = os.getenv("DEXTER_OPENROUTER_REFERER", "").strip()
    if referer:
        headers["HTTP-Referer"] = referer

    title = os.getenv("DEXTER_OPENROUTER_TITLE", "Dexter").strip()
    if title:
        headers["X-Title"] = title

    return headers


def chat_completion(
    messages: list[dict[str, str]],
    model: str = DEFAULT_OPENROUTER_MODEL,
    timeout: int = 120,
    options: dict[str, Any] | None = None,
    response_format: str | None = None,
) -> str:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("OpenRouter API key is not configured.")

    payload: dict[str, Any] = {
        "model": model or DEFAULT_OPENROUTER_MODEL,
        "messages": messages,
    }

    max_tokens = _max_tokens(options)
    if max_tokens:
        payload["max_tokens"] = max_tokens

    temperature = _temperature(options)
    if temperature is not None:
        payload["temperature"] = temperature

    use_response_format = os.getenv(
        "DEXTER_OPENROUTER_RESPONSE_FORMAT",
        "false",
    ).lower() in {"1", "true", "yes"}
    if response_format == "json" and use_response_format:
        payload["response_format"] = {"type": "json_object"}

    response = requests.post(
        OPENROUTER_CHAT_URL,
        headers=_headers(api_key),
        json=payload,
        timeout=timeout,
    )

    if not response.ok:
        detail = response.text[:1000]
        raise RuntimeError(
            f"OpenRouter API request failed with HTTP {response.status_code}: {detail}"
        )

    text = _extract_output_text(response.json())
    if not text:
        raise RuntimeError("OpenRouter API returned no output text.")

    return text


def status() -> dict[str, Any]:
    return {
        "configured": is_configured(),
        "model": DEFAULT_OPENROUTER_MODEL,
        "base_url": OPENROUTER_BASE_URL,
        "chat_url": OPENROUTER_CHAT_URL,
    }
