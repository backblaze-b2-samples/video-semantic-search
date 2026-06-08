"""Transcription adapter (Whisper). Provider SDKs are imported lazily so the
module imports cleanly without the SDK installed or a key set."""

import logging

from app.config import settings
from app.repo.errors import ProviderNotConfiguredError

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    if settings.transcription_provider == "local":
        return True
    return bool(settings.openai_api_key)


def transcribe(audio_path: str) -> dict:
    """Transcribe audio to ``{language, duration, segments:[{start,end,text}]}``.

    The service maps the returned dict into a typed ``Transcript``.
    """
    if not is_configured():
        raise ProviderNotConfiguredError(
            "No transcription provider configured. Set OPENAI_API_KEY, or "
            "TRANSCRIPTION_PROVIDER=local with faster-whisper installed."
        )
    if settings.transcription_provider == "local":
        return _transcribe_local(audio_path)
    return _transcribe_openai(audio_path)


def _transcribe_openai(audio_path: str) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    with open(audio_path, "rb") as fh:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=fh,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    segments: list[dict] = []
    for s in getattr(resp, "segments", None) or []:
        start = getattr(s, "start", None)
        end = getattr(s, "end", None)
        if start is None or end is None:
            continue
        segments.append(
            {
                "start": float(start),
                "end": float(end),
                "text": (getattr(s, "text", "") or "").strip(),
            }
        )
    return {
        "language": getattr(resp, "language", None),
        "duration": getattr(resp, "duration", None),
        "segments": segments,
    }


def _transcribe_local(audio_path: str) -> dict:
    # First-feature: wire faster-whisper here. See docs/features/transcription.md.
    raise NotImplementedError(
        "Local transcription (faster-whisper) is not wired yet. Use "
        "TRANSCRIPTION_PROVIDER=openai with OPENAI_API_KEY, or implement "
        "_transcribe_local — see docs/features/transcription.md."
    )
