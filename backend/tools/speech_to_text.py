from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from backend.utils.logger import log_action


MODEL_SIZE = os.getenv("DEXTER_STT_MODEL", "tiny.en")
COMPUTE_TYPE = os.getenv("DEXTER_STT_COMPUTE_TYPE", "int8")

_FAST_MODEL: Any = None
_WHISPER_MODEL: Any = None


def _load_faster_whisper():
    global _FAST_MODEL

    if _FAST_MODEL is not None:
        return _FAST_MODEL

    from faster_whisper import WhisperModel

    _FAST_MODEL = WhisperModel(MODEL_SIZE, device="cpu", compute_type=COMPUTE_TYPE)
    return _FAST_MODEL


def _load_openai_whisper():
    global _WHISPER_MODEL

    if _WHISPER_MODEL is not None:
        return _WHISPER_MODEL

    import whisper

    _WHISPER_MODEL = whisper.load_model(MODEL_SIZE)
    return _WHISPER_MODEL


def _transcribe_file(path: Path) -> dict[str, Any]:
    try:
        model = _load_faster_whisper()
        segments, info = model.transcribe(
            str(path),
            beam_size=1,
            vad_filter=True,
            temperature=0,
            language="en",
            condition_on_previous_text=False,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        if not text:
            segments, info = model.transcribe(
                str(path),
                beam_size=1,
                vad_filter=False,
                temperature=0,
                language="en",
                condition_on_previous_text=False,
            )
            text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        return {
            "ok": True,
            "text": text,
            "engine": "faster-whisper",
            "language": getattr(info, "language", "en"),
        }
    except Exception as faster_error:
        try:
            model = _load_openai_whisper()
            result = model.transcribe(str(path), fp16=False, language="en")
            return {
                "ok": True,
                "text": str(result.get("text", "")).strip(),
                "engine": "openai-whisper",
                "language": result.get("language", "en"),
                "fallback_from": str(faster_error),
            }
        except Exception as whisper_error:
            return {
                "ok": False,
                "error": (
                    "Speech transcription failed. Install faster-whisper and make sure "
                    "ffmpeg/audio decoding is available."
                ),
                "details": {
                    "faster_whisper": str(faster_error),
                    "openai_whisper": str(whisper_error),
                },
            }


async def transcribe_audio(file: UploadFile) -> dict[str, Any]:
    suffix = Path(file.filename or "speech.webm").suffix or ".webm"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        temp_path = Path(temp.name)
        temp.write(await file.read())

    try:
        result = await asyncio.to_thread(_transcribe_file, temp_path)
        log_action(
            "speech_transcribed",
            {
                "ok": result.get("ok"),
                "engine": result.get("engine"),
                "text_length": len(result.get("text", "")),
            },
        )
        return result
    finally:
        temp_path.unlink(missing_ok=True)
