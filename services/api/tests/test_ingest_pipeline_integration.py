"""Integration coverage for the video ingest pipeline.

The default test is hermetic: it mocks repo adapters for B2, ffmpeg, Whisper,
and embeddings while exercising the real service orchestration, typed artifact
persistence, transcript chunking, and semantic search round-trip.

The live-provider test is opt-in via environment variables so developers can
verify the same flow against real B2/OpenAI credentials without making CI
depend on external services.
"""

import json
import mimetypes
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import settings
from app.repo import embeddings, llm, media, transcription, video_store
from app.repo.b2_client import get_s3_client
from app.service import ingest
from app.service import search as search_svc
from app.service import videos as videos_svc
from app.types import (
    CompletedPart,
    CompleteUploadRequest,
    CreateUploadRequest,
    SearchRequest,
    Video,
    VideoStatus,
)
from app.types.formatting import humanize_bytes

PLACEHOLDER_VALUES = {
    "your_b2_endpoint",
    "your_application_key_id",
    "your_application_key",
    "your-bucket-name",
}


def _install_memory_video_store(monkeypatch) -> dict[str, dict]:
    objects: dict[str, dict] = {}

    def put_json(key: str, payload: dict) -> None:
        objects[key] = json.loads(json.dumps(payload))

    def get_json(key: str) -> dict | None:
        if key not in objects:
            return None
        return json.loads(json.dumps(objects[key]))

    def list_video_ids() -> list[str]:
        prefix = f"{settings.video_prefix}videos/"
        ids = {
            key[len(prefix) :].split("/", 1)[0]
            for key in objects
            if key.startswith(prefix) and "/" in key[len(prefix) :]
        }
        return sorted(ids)

    monkeypatch.setattr(video_store, "put_json", put_json)
    monkeypatch.setattr(video_store, "get_json", get_json)
    monkeypatch.setattr(video_store, "list_video_ids", list_video_ids)
    monkeypatch.setattr(video_store, "create_multipart", lambda *_args: "upload-1")
    monkeypatch.setattr(
        video_store,
        "presign_part",
        lambda key, _upload_id, part_number: f"https://b2.example/{key}?part={part_number}",
    )
    monkeypatch.setattr(video_store, "complete_multipart", lambda *_args: None)
    monkeypatch.setattr(
        video_store,
        "playback_url",
        lambda key: f"https://b2.example/playback/{key}",
    )
    return objects


def test_ingest_pipeline_persists_artifacts_and_searches_with_mocked_providers(
    monkeypatch,
    tmp_path,
):
    objects = _install_memory_video_store(monkeypatch)
    source_path = tmp_path / "source.mp4"
    audio_path = tmp_path / "audio.m4a"
    source_path.write_bytes(b"fake video bytes")
    audio_path.write_bytes(b"fake audio bytes")

    downloaded_keys: list[str] = []
    monkeypatch.setattr(
        media,
        "download_to_temp",
        lambda key: downloaded_keys.append(key) or str(source_path),
    )
    monkeypatch.setattr(media, "extract_audio", lambda path: str(audio_path))
    monkeypatch.setattr(media, "probe_duration", lambda path: 24.0)

    storage_text = (
        "Backblaze B2 stores the source video, transcript, embeddings, "
        "and generated artifacts for the semantic search app. "
    ) * 12
    dashboard_text = (
        "The dashboard reports video status, upload activity, and library metrics for operators. "
    ) * 14
    monkeypatch.setattr(transcription, "is_configured", lambda: True)
    monkeypatch.setattr(
        transcription,
        "transcribe",
        lambda audio: {
            "language": "en",
            "duration": 24.0,
            "segments": [
                {"start": 0.0, "end": 12.0, "text": storage_text},
                {"start": 12.0, "end": 24.0, "text": dashboard_text},
            ],
        },
    )

    def vector_for(text: str) -> list[float]:
        normalized = text.lower()
        if "generated artifacts" in normalized or "where does the app store" in normalized:
            return [1.0, 0.0, 0.0]
        return [0.0, 1.0, 0.0]

    monkeypatch.setattr(embeddings, "is_configured", lambda: True)
    monkeypatch.setattr(embeddings, "model_name", lambda: "fake-embedding-001")
    monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [vector_for(t) for t in texts])
    monkeypatch.setattr(embeddings, "embed_query", vector_for)
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(
        llm,
        "synthesize_answer",
        lambda question, clips: "Artifacts are stored in Backblaze B2.",
    )

    upload = videos_svc.create_upload(
        CreateUploadRequest(
            filename="Provider Demo.mp4",
            size_bytes=len(source_path.read_bytes()),
            content_type="video/mp4",
        )
    )
    completed = videos_svc.complete_upload(
        CompleteUploadRequest(
            video_id=upload.video_id,
            source_key=upload.source_key,
            upload_id=upload.upload_id,
            title="Provider Demo.mp4",
            size_bytes=len(source_path.read_bytes()),
            content_type="video/mp4",
            parts=[CompletedPart(part_number=1, etag='"etag-1"')],
        )
    )

    assert completed.status == VideoStatus.uploaded

    ingest.run_pipeline(upload.video_id)

    assert downloaded_keys == [upload.source_key]
    video = videos_svc.get_video(upload.video_id)
    assert video.status == VideoStatus.ready
    assert video.duration_seconds == 24.0
    assert video.chunk_count == 2
    assert video.error is None

    transcript = objects[video_store.transcript_key(upload.video_id)]
    assert transcript["video_id"] == upload.video_id
    assert transcript["language"] == "en"
    assert len(transcript["segments"]) == 2

    index = objects[video_store.embeddings_key(upload.video_id)]
    assert index["video_id"] == upload.video_id
    assert index["model"] == "fake-embedding-001"
    assert index["dim"] == 3
    assert len(index["chunks"]) == 2

    response = search_svc.search(
        SearchRequest(
            question="Where does the app store generated artifacts?",
            video_id=upload.video_id,
            top_k=1,
            synthesize=True,
        )
    )

    assert response.provider_configured is True
    assert response.answer == "Artifacts are stored in Backblaze B2."
    assert len(response.clips) == 1
    clip = response.clips[0]
    assert clip.video_id == upload.video_id
    assert clip.start == 0.0
    assert clip.end == 12.0
    assert "Backblaze B2 stores" in clip.text
    assert clip.score == pytest.approx(1.0)
    assert clip.playback_url == f"https://b2.example/playback/{upload.source_key}"


def test_live_ingest_pipeline_round_trip_against_providers():
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

    sample = os.getenv("LIVE_INGEST_VIDEO_PATH")
    if not sample or not Path(sample).is_file():
        pytest.skip("Set LIVE_INGEST_VIDEO_PATH to a small speech video file.")

    path = Path(sample)
    video_id = f"live-provider-smoke-{uuid.uuid4().hex[:8]}"
    content_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
    source_key = video_store.source_key(video_id, path.suffix.lstrip(".") or "mp4")

    client = get_s3_client()
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

    try:
        client.upload_file(
            str(path),
            settings.b2_bucket_name,
            source_key,
            ExtraArgs={"ContentType": content_type},
        )

        ingest.run_pipeline(video_id)

        video = videos_svc.get_video(video_id)
        assert video.status == VideoStatus.ready
        assert video.error is None
        assert video.chunk_count and video.chunk_count > 0

        transcript = video_store.get_json(video_store.transcript_key(video_id))
        assert transcript and transcript.get("segments")
        index = video_store.get_json(video_store.embeddings_key(video_id))
        assert index and index.get("chunks")

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
        video_store.delete_video_tree(video_id)
