"""Hermetic integration coverage for the video ingest pipeline.

This test mocks B2, ffmpeg, transcription, embeddings, and LLM adapters while
exercising the real service orchestration, typed artifact persistence,
transcript chunking, and semantic search round-trip.
"""

import pytest

from app.repo import embeddings, llm, media, transcription, video_store
from app.service import ingest
from app.service import search as search_svc
from app.service import videos as videos_svc
from app.types import SearchRequest, VideoStatus
from tests.ingest_helpers import (
    completion_request,
    create_pending_upload,
    install_memory_video_store,
)


def test_ingest_pipeline_persists_artifacts_and_searches_with_mocked_providers(
    monkeypatch,
    tmp_path,
):
    store = install_memory_video_store(monkeypatch)
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

    upload = create_pending_upload()
    completion = videos_svc.complete_upload(completion_request(upload))
    completed = completion.video

    assert completion.start_pipeline is True
    assert completed.status == VideoStatus.uploaded
    assert completed.pending_upload_id is None
    assert store.completed_multipart == [
        (
            upload.source_key,
            upload.upload_id,
            [{"PartNumber": 1, "ETag": '"etag-1"'}],
        )
    ]

    ingest.run_pipeline(upload.video_id)

    assert downloaded_keys == [upload.source_key]
    video = videos_svc.get_video(upload.video_id)
    assert video.status == VideoStatus.ready
    assert video.duration_seconds == 24.0
    assert video.chunk_count == 2
    assert video.error is None

    transcript = store.objects[video_store.transcript_key(upload.video_id)]
    assert transcript["video_id"] == upload.video_id
    assert transcript["language"] == "en"
    assert len(transcript["segments"]) == 2

    index = store.objects[video_store.embeddings_key(upload.video_id)]
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
