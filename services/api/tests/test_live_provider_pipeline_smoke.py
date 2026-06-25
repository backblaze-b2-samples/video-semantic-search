"""Opt-in live provider smoke coverage for the ingest pipeline.

These tests are skipped by default. When explicitly enabled, the live smoke test
uploads a vetted fixture to B2 and runs the provider pipeline from that source
object through ffmpeg, transcription, embeddings, and optional answer synthesis.
"""

import os
import shutil
import uuid
from datetime import UTC, datetime
from queue import Empty

import pytest

from app.config import settings
from app.repo import video_store
from app.repo.b2_client import get_s3_client
from app.service import search as search_svc
from app.service import videos as videos_svc
from app.types import SearchRequest, Video, VideoStatus
from app.types.formatting import humanize_bytes
from tests import ingest_helpers
from tests.ingest_helpers import (
    LIVE_DEFAULT_PHASE_TIMEOUT_SECONDS,
    LIVE_DEFAULT_PIPELINE_TIMEOUT_SECONDS,
    LIVE_MAX_FIXTURE_BYTES,
    live_phase_deadline,
    live_timeout_seconds,
    run_live_pipeline_with_deadline,
    validated_live_fixture,
)

PLACEHOLDER_VALUES = {
    "your_b2_endpoint",
    "your_application_key_id",
    "your_application_key",
    "your-bucket-name",
}


def test_live_fixture_rejects_paths_outside_fixture_dir(monkeypatch, tmp_path):
    secret_path = tmp_path / ".env"
    secret_path.write_text("OPENAI_API_KEY=secret\n")
    monkeypatch.setenv("LIVE_INGEST_VIDEO_PATH", str(secret_path))

    with pytest.raises(pytest.fail.Exception, match="vetted fixture"):
        validated_live_fixture()


def test_live_fixture_rejects_oversized_video(monkeypatch, tmp_path):
    fixture_dir = tmp_path / "live-ingest"
    fixture_dir.mkdir()
    video_path = fixture_dir / "too-large.mp4"
    with video_path.open("wb") as fh:
        fh.truncate(LIVE_MAX_FIXTURE_BYTES + 1)
    monkeypatch.setattr(ingest_helpers, "LIVE_FIXTURE_DIR", fixture_dir)
    monkeypatch.setenv("LIVE_INGEST_VIDEO_PATH", str(video_path))

    with pytest.raises(pytest.fail.Exception, match="25 MiB"):
        validated_live_fixture()


def test_live_pipeline_deadline_fails_when_child_reports_no_result(monkeypatch):
    class EmptyQueue:
        def get_nowait(self):
            raise Empty

    class SuccessfulProcess:
        exitcode = 0

        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def join(self, _timeout):
            pass

        def is_alive(self):
            return False

    monkeypatch.setattr(ingest_helpers, "Queue", EmptyQueue)
    monkeypatch.setattr(ingest_helpers, "Process", SuccessfulProcess)

    with pytest.raises(pytest.fail.Exception, match="without reporting a result"):
        run_live_pipeline_with_deadline("video-id", 1)


def test_live_provider_pipeline_smoke_against_uploaded_source():
    if os.getenv("RUN_LIVE_INGEST_TEST") != "1":
        pytest.skip("Set RUN_LIVE_INGEST_TEST=1 to run the live provider smoke test.")

    required_settings = {
        "OPENAI_API_KEY": settings.openai_api_key,
        "B2_APPLICATION_KEY_ID": settings.b2_application_key_id,
        "B2_APPLICATION_KEY": settings.b2_application_key,
        "B2_BUCKET_NAME": settings.b2_bucket_name,
        "B2_ENDPOINT": settings.b2_endpoint,
    }
    missing = [
        name
        for name, value in required_settings.items()
        if not value or value in PLACEHOLDER_VALUES
    ]
    if missing:
        pytest.skip("Missing live ingest settings: " + ", ".join(missing))

    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("ffmpeg and ffprobe are required for live ingest verification.")

    path, content_type = validated_live_fixture()
    phase_timeout = live_timeout_seconds(
        "LIVE_INGEST_PHASE_TIMEOUT_SECONDS",
        LIVE_DEFAULT_PHASE_TIMEOUT_SECONDS,
    )
    pipeline_timeout = live_timeout_seconds(
        "LIVE_INGEST_PIPELINE_TIMEOUT_SECONDS",
        LIVE_DEFAULT_PIPELINE_TIMEOUT_SECONDS,
    )
    video_id = f"live-provider-smoke-{uuid.uuid4().hex[:8]}"
    source_key = video_store.source_key(video_id, path.suffix.lstrip(".") or "mp4")

    client = get_s3_client()
    try:
        with live_phase_deadline("writing live video metadata to B2", phase_timeout):
            video_store.put_json(
                video_store.meta_key(video_id),
                Video(
                    video_id=video_id,
                    title=path.name,
                    status=VideoStatus.uploaded,
                    source_key=source_key,
                    size_bytes=path.stat().st_size,
                    size_human=humanize_bytes(path.stat().st_size),
                    content_type=content_type,
                    created_at=datetime.now(UTC),
                ).model_dump(mode="json"),
            )

        with live_phase_deadline("uploading the live fixture to B2", phase_timeout):
            client.upload_file(
                str(path),
                settings.b2_bucket_name,
                source_key,
                ExtraArgs={"ContentType": content_type},
            )

        run_live_pipeline_with_deadline(video_id, pipeline_timeout)

        video = videos_svc.get_video(video_id)
        assert video.status == VideoStatus.ready
        assert video.error is None
        assert video.chunk_count and video.chunk_count > 0

        transcript = video_store.get_json(video_store.transcript_key(video_id))
        assert transcript and transcript.get("segments")
        index = video_store.get_json(video_store.embeddings_key(video_id))
        assert index and index.get("chunks")

        with live_phase_deadline(
            "running semantic search against live artifacts",
            phase_timeout,
        ):
            response = search_svc.search(
                SearchRequest(
                    question=os.getenv("LIVE_INGEST_QUERY", "What is discussed in this video?"),
                    video_id=video_id,
                    top_k=1,
                    synthesize=bool(settings.anthropic_api_key),
                )
            )
        assert response.provider_configured is True
        assert response.clips
        if settings.anthropic_api_key:
            assert response.answer
    finally:
        with live_phase_deadline(
            "deleting temporary live-provider B2 objects",
            phase_timeout,
        ):
            video_store.delete_video_tree(video_id)
