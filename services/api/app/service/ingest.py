"""Ingest pipeline: extract audio → transcribe → chunk → embed → persist the
index to B2. Runs as a FastAPI BackgroundTask (no external job queue — see
docs/RELIABILITY.md). Status is persisted to meta.json at every stage so the
Library reflects progress, and the whole thing degrades gracefully when an AI
provider isn't configured."""

import logging

from app.repo import ProviderNotConfiguredError, embeddings, media, transcription, video_store
from app.service import videos as videos_svc
from app.service.transcript import chunk_transcript
from app.types import ChunkEmbedding, EmbeddingIndex, Transcript, VideoStatus

logger = logging.getLogger(__name__)


def run_pipeline(video_id: str) -> None:
    video = videos_svc.try_get(video_id)
    if not video:
        logger.warning("Pipeline: video %s not found", video_id)
        return

    if not (transcription.is_configured() and embeddings.is_configured()):
        videos_svc.update_status(
            video_id,
            VideoStatus.uploaded,
            error="AI provider not configured — set OPENAI_API_KEY to "
            "transcribe and index this video.",
        )
        logger.info("Pipeline skipped for %s: provider not configured", video_id)
        return

    try:
        videos_svc.update_status(video_id, VideoStatus.extracting)
        local_video = media.download_to_temp(video.source_key)
        audio_path = media.extract_audio(local_video)
        duration = media.probe_duration(local_video)

        videos_svc.update_status(
            video_id, VideoStatus.transcribing, duration_seconds=duration
        )
        raw = transcription.transcribe(audio_path)
        transcript = Transcript(
            video_id=video_id,
            language=raw.get("language"),
            duration_seconds=raw.get("duration") or duration,
            segments=raw.get("segments", []),
        )
        video_store.put_json(
            video_store.transcript_key(video_id),
            transcript.model_dump(mode="json"),
        )

        videos_svc.update_status(video_id, VideoStatus.chunking)
        chunks = chunk_transcript(transcript)

        videos_svc.update_status(
            video_id, VideoStatus.embedding, chunk_count=len(chunks)
        )
        vectors = embeddings.embed_texts([c.text for c in chunks]) if chunks else []
        index = EmbeddingIndex(
            video_id=video_id,
            model=embeddings.model_name(),
            dim=len(vectors[0]) if vectors else 0,
            chunks=[
                ChunkEmbedding(
                    chunk_id=c.chunk_id,
                    start=c.start,
                    end=c.end,
                    text=c.text,
                    vector=v,
                )
                for c, v in zip(chunks, vectors, strict=False)
            ],
        )
        video_store.put_json(
            video_store.embeddings_key(video_id), index.model_dump(mode="json")
        )

        videos_svc.update_status(
            video_id,
            VideoStatus.ready,
            duration_seconds=transcript.duration_seconds,
            chunk_count=len(chunks),
        )
        logger.info("Pipeline complete for %s: %d chunks", video_id, len(chunks))
    except ProviderNotConfiguredError as e:
        videos_svc.update_status(video_id, VideoStatus.uploaded, error=str(e))
    except Exception as e:  # pipeline must never crash the background worker
        logger.exception("Pipeline failed for %s", video_id)
        videos_svc.update_status(video_id, VideoStatus.failed, error=str(e)[:300])
