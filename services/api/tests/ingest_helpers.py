import json
import mimetypes
import os
import signal
from contextlib import contextmanager
from dataclasses import dataclass, field
from multiprocessing import Process, Queue
from pathlib import Path
from queue import Empty

import pytest

from app.repo import video_store
from app.service import ingest
from app.service import videos as videos_svc
from app.types import (
    CompletedPart,
    CompleteUploadRequest,
    CreateUploadRequest,
)

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


def install_memory_video_store(monkeypatch) -> MemoryVideoStore:
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


def completion_request(
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


def create_pending_upload(filename: str = "Provider Demo.mp4"):
    return videos_svc.create_upload(
        CreateUploadRequest(
            filename=filename,
            size_bytes=16,
            content_type="video/mp4",
        )
    )


def live_timeout_seconds(env_name: str, default: int) -> int:
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
def live_phase_deadline(phase: str, seconds: int):
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


def run_pipeline_for_live_test(video_id: str, result_queue) -> None:
    try:
        ingest.run_pipeline(video_id)
    except Exception as exc:
        result_queue.put(("error", repr(exc)))
    else:
        result_queue.put(("ok", None))


def run_live_pipeline_with_deadline(video_id: str, seconds: int) -> None:
    result_queue = Queue()
    process = Process(
        target=run_pipeline_for_live_test,
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
        pytest.fail("Live ingest pipeline exited without reporting a result.")
    if status == "error":
        pytest.fail(f"Live ingest pipeline failed: {detail}")


def validated_live_fixture() -> tuple[Path, str]:
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
