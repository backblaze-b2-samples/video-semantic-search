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
import signal
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from multiprocessing import Process, Queue
from pathlib import Path
from queue import Empty

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
LIVE_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "live-ingest"
LIVE_VIDEO_EXTENSIONS = {".m4v", ".mov", ".mp4", ".webm"}
LIVE_MAX_FIXTURE_BYTES = 25 * 1024 * 1024
LIVE_DEFAULT_PHASE_TIMEOUT_SECONDS = 120
LIVE_DEFAULT_PIPELINE_TIMEOUT_SECONDS = 600


@dataclass
class MemoryVideoStore:
    objects: dict[str, dict] = field(default_factory=dict)
    video_ids: set[str] = field(default_factory=set)
    completed_multipart: list[tuple[str, str, list[dict]]] = field(default_factory=list)


class LivePhaseTimeoutError(Exception):
    pass


def _install_memory_video_store(monkeypatch) -> MemoryVideoStore:
    store = MemoryVideoStore()

    def put_json(key: str, payload: dict) -> None:
        serialized = json.loads(json.dumps(payload))
        store.objects[key] = serialized
        video_id = serialized.get("video_id")
        if video_id and key == video_store.meta_key(video_id):
            store.video_ids.add(video_id)

    def get_json(key: str) -> dict | None:
        if key not in store.objects:
            return None
        return json.loads(json.dumps(store.objects[key]))

    def list_video_ids() -> list[str]:
        return sorted(store.video_ids)

    def complete_multipart(key: str, upload_id: str, parts: list[dict]) -> None:
        store.completed_multipart.append((key, upload_id, parts))

    monkeypatch.setattr(video_store, "put_json", put_json)
    monkeypatch.setattr(video_store, "get_json", get_json)
    monkeypatch.setattr(video_store, "list_video_ids", list_video_ids)
    monkeypatch.setattr(video_store, "create_multipart", lambda *_args: "upload-1")
    monkeypatch.setattr(
        video_store,
        "presign_part",
        lambda key, _upload_id, part_number: f"https://b2.example/{key}?part={part_number}",
    )
    monkeypatch.setattr(video_store, "complete_multipart", complete_multipart)
    monkeypatch.setattr(
        video_store,
        "playback_url",
        lambda key: f"https://b2.example/playback/{key}",
    )
    return store


def _completion_request(
    upload,
    *,
    video_id: str | None = None,
    source_key: str | None = None,
    upload_id: str | None = None,
) -> CompleteUploadRequest:
    return CompleteUploadRequest(
        video_id=video_id or upload.video_id,
        source_key=source_key or upload.source_key,
        upload_id=upload_id or upload.upload_id,
        title="Provider Demo.mp4",
        size_bytes=16,
        content_type="video/mp4",
        parts=[CompletedPart(part_number=1, etag='"etag-1"')],
    )


def _create_pending_upload(filename: str = "Provider Demo.mp4"):
    return videos_svc.create_upload(
        CreateUploadRequest(
            filename=filename,
            size_bytes=16,
            content_type="video/mp4",
        )
    )


def _live_timeout_seconds(env_name: str, default: int) -> int:
    raw = os.getenv(env_name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        pytest.fail(f"{env_name} must be an integer number of seconds.")
    if value <= 0:
        pytest.fail(f"{env_name} must be greater than zero.")
    return value


@contextmanager
def _live_phase_deadline(phase: str, seconds: int):
    if not hasattr(signal, "SIGALRM"):
        pytest.skip("Live provider smoke test deadlines require signal.SIGALRM.")

    def timeout_handler(_signum, _frame):
        raise LivePhaseTimeoutError(f"Timed out after {seconds}s while {phase}.")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    except LivePhaseTimeoutError as exc:
        pytest.fail(str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _run_pipeline_for_live_test(video_id: str, result_queue) -> None:
    try:
        ingest.run_pipeline(video_id)
    except Exception as exc:
        result_queue.put(("error", repr(exc)))
    else:
        result_queue.put(("ok", None))


def _run_live_pipeline_with_deadline(video_id: str, seconds: int) -> None:
    result_queue = Queue()
    process = Process(
        target=_run_pipeline_for_live_test,
        args=(video_id, result_queue),
        daemon=True,
    )
    process.start()
    process.join(seconds)
    if process.is_alive():
        process.terminate()
        process.join(10)
        pytest.fail(
            "Timed out after "
            f"{seconds}s while running ffmpeg, transcription, and embedding pipeline."
        )
    if process.exitcode != 0:
        pytest.fail(
            f"Live ingest pipeline process exited with code {process.exitcode} before completing."
        )
    try:
        status, detail = result_queue.get_nowait()
    except Empty:
        return
    if status == "error":
        pytest.fail(f"Live ingest pipeline failed: {detail}")


def _validated_live_fixture() -> tuple[Path, str]:
    sample = os.getenv("LIVE_INGEST_VIDEO_PATH")
    if not sample:
        pytest.skip(
            "Set LIVE_INGEST_VIDEO_PATH to an approved small speech video under "
            f"{LIVE_FIXTURE_DIR}."
        )

    try:
        path = Path(sample).expanduser().resolve(strict=True)
    except FileNotFoundError:
        pytest.fail(f"LIVE_INGEST_VIDEO_PATH does not exist: {sample}")

    fixture_dir = LIVE_FIXTURE_DIR.resolve()
    if not path.is_relative_to(fixture_dir):
        pytest.fail(f"LIVE_INGEST_VIDEO_PATH must point to a vetted fixture under {fixture_dir}.")
    if not path.is_file():
        pytest.fail(f"LIVE_INGEST_VIDEO_PATH must be a regular file: {path}")
    if path.suffix.lower() not in LIVE_VIDEO_EXTENSIONS:
        pytest.fail(
            "LIVE_INGEST_VIDEO_PATH must use one of these extensions: "
            + ", ".join(sorted(LIVE_VIDEO_EXTENSIONS))
        )

    size_bytes = path.stat().st_size
    if size_bytes <= 0:
        pytest.fail("LIVE_INGEST_VIDEO_PATH must not be empty.")
    if size_bytes > LIVE_MAX_FIXTURE_BYTES:
        pytest.fail("LIVE_INGEST_VIDEO_PATH must be 25 MiB or smaller before upload.")

    content_type = mimetypes.guess_type(path.name)[0] or ""
    if not content_type.startswith("video/"):
        pytest.fail("LIVE_INGEST_VIDEO_PATH must resolve to a video MIME type.")
    return path, content_type


def test_complete_upload_rejects_missing_pending_metadata(monkeypatch):
    store = _install_memory_video_store(monkeypatch)
    request = CompleteUploadRequest(
        video_id="missing-video",
        source_key=video_store.source_key("missing-video"),
        upload_id="upload-1",
        title="Missing.mp4",
        size_bytes=16,
        content_type="video/mp4",
        parts=[CompletedPart(part_number=1, etag='"etag-1"')],
    )

    with pytest.raises(ValueError, match="Pending video upload not found"):
        videos_svc.complete_upload(request)

    assert store.completed_multipart == []
    assert video_store.get_json(video_store.meta_key("missing-video")) is None


def test_complete_upload_rejects_mismatched_source_key(monkeypatch):
    store = _install_memory_video_store(monkeypatch)
    first_upload = _create_pending_upload("First.mp4")
    second_upload = _create_pending_upload("Second.mp4")
    assert videos_svc.get_video(second_upload.video_id).pending_upload_id == second_upload.upload_id

    with pytest.raises(ValueError, match="source_key"):
        videos_svc.complete_upload(
            _completion_request(second_upload, source_key=first_upload.source_key)
        )

    assert store.completed_multipart == []
    assert videos_svc.get_video(second_upload.video_id).status == VideoStatus.uploading
    assert videos_svc.get_video(second_upload.video_id).source_key == second_upload.source_key


def test_complete_upload_rejects_mismatched_upload_id(monkeypatch):
    store = _install_memory_video_store(monkeypatch)
    upload = _create_pending_upload()
    assert videos_svc.get_video(upload.video_id).pending_upload_id == upload.upload_id

    with pytest.raises(ValueError, match="upload_id"):
        videos_svc.complete_upload(_completion_request(upload, upload_id="wrong-upload"))

    assert store.completed_multipart == []
    video = videos_svc.get_video(upload.video_id)
    assert video.status == VideoStatus.uploading
    assert video.pending_upload_id == upload.upload_id


def test_ingest_pipeline_persists_artifacts_and_searches_with_mocked_providers(
    monkeypatch,
    tmp_path,
):
    store = _install_memory_video_store(monkeypatch)
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

    upload = _create_pending_upload()
    completed = videos_svc.complete_upload(_completion_request(upload))

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

    path, content_type = _validated_live_fixture()
    phase_timeout = _live_timeout_seconds(
        "LIVE_INGEST_PHASE_TIMEOUT_SECONDS",
        LIVE_DEFAULT_PHASE_TIMEOUT_SECONDS,
    )
    pipeline_timeout = _live_timeout_seconds(
        "LIVE_INGEST_PIPELINE_TIMEOUT_SECONDS",
        LIVE_DEFAULT_PIPELINE_TIMEOUT_SECONDS,
    )
    video_id = f"live-provider-smoke-{uuid.uuid4().hex[:8]}"
    source_key = video_store.source_key(video_id, path.suffix.lstrip(".") or "mp4")

    client = get_s3_client()
    try:
        with _live_phase_deadline("writing live video metadata to B2", phase_timeout):
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

        with _live_phase_deadline("uploading the live fixture to B2", phase_timeout):
            client.upload_file(
                str(path),
                settings.b2_bucket_name,
                source_key,
                ExtraArgs={"ContentType": content_type},
            )

        _run_live_pipeline_with_deadline(video_id, pipeline_timeout)

        video = videos_svc.get_video(video_id)
        assert video.status == VideoStatus.ready
        assert video.error is None
        assert video.chunk_count and video.chunk_count > 0

        transcript = video_store.get_json(video_store.transcript_key(video_id))
        assert transcript and transcript.get("segments")
        index = video_store.get_json(video_store.embeddings_key(video_id))
        assert index and index.get("chunks")

        with _live_phase_deadline(
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
        with _live_phase_deadline(
            "deleting temporary live-provider B2 objects",
            phase_timeout,
        ):
            video_store.delete_video_tree(video_id)
