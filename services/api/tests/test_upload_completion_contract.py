import pytest
from fastapi import BackgroundTasks

from app.repo import video_store
from app.runtime import videos as videos_runtime
from app.service import videos as videos_svc
from app.types import (
    CompletedPart,
    CompleteUploadRequest,
    VideoStatus,
)
from tests.ingest_helpers import (
    completion_request,
    create_pending_upload,
    install_memory_video_store,
)


def test_complete_upload_rejects_missing_pending_metadata(monkeypatch):
    store = install_memory_video_store(monkeypatch)
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
    store = install_memory_video_store(monkeypatch)
    first_upload = create_pending_upload("First.mp4")
    second_upload = create_pending_upload("Second.mp4")
    assert videos_svc.get_video(second_upload.video_id).pending_upload_id == second_upload.upload_id

    with pytest.raises(ValueError, match="source_key"):
        videos_svc.complete_upload(
            completion_request(second_upload, source_key=first_upload.source_key)
        )

    assert store.completed_multipart == []
    assert videos_svc.get_video(second_upload.video_id).status == VideoStatus.uploading
    assert videos_svc.get_video(second_upload.video_id).source_key == second_upload.source_key


def test_complete_upload_rejects_mismatched_upload_id(monkeypatch):
    store = install_memory_video_store(monkeypatch)
    upload = create_pending_upload()
    assert videos_svc.get_video(upload.video_id).pending_upload_id == upload.upload_id

    with pytest.raises(ValueError, match="upload_id"):
        videos_svc.complete_upload(completion_request(upload, upload_id="wrong-upload"))

    assert store.completed_multipart == []
    video = videos_svc.get_video(upload.video_id)
    assert video.status == VideoStatus.uploading
    assert video.pending_upload_id == upload.upload_id


def test_complete_upload_allows_legacy_metadata_without_pending_upload_id(monkeypatch):
    store = install_memory_video_store(monkeypatch)
    upload = create_pending_upload()
    store.objects[video_store.meta_key(upload.video_id)].pop("pending_upload_id")

    completion = videos_svc.complete_upload(completion_request(upload))

    assert completion.start_pipeline is True
    assert store.completed_multipart == [
        (
            upload.source_key,
            upload.upload_id,
            [{"PartNumber": 1, "ETag": '"etag-1"'}],
        )
    ]
    video = completion.video
    assert video.status == VideoStatus.uploaded
    assert video.pending_upload_id is None


def test_complete_upload_is_idempotent_after_success(monkeypatch):
    store = install_memory_video_store(monkeypatch)
    upload = create_pending_upload()
    request = completion_request(upload)

    first = videos_svc.complete_upload(request)
    second = videos_svc.complete_upload(request)

    assert first.start_pipeline is True
    assert second.start_pipeline is False
    assert second.video.status == VideoStatus.uploaded
    assert second.video.pending_upload_id is None
    assert store.completed_multipart == [
        (
            upload.source_key,
            upload.upload_id,
            [{"PartNumber": 1, "ETag": '"etag-1"'}],
        )
    ]


async def test_complete_upload_endpoint_skips_pipeline_for_duplicate(monkeypatch):
    store = install_memory_video_store(monkeypatch)
    upload = create_pending_upload()
    request = completion_request(upload)
    videos_svc.complete_upload(request)

    background_tasks = BackgroundTasks()
    video = await videos_runtime.complete_upload_endpoint(request, background_tasks)

    assert video.status == VideoStatus.uploaded
    assert background_tasks.tasks == []
    assert len(store.completed_multipart) == 1


def test_complete_upload_rejects_mismatched_source_after_success(monkeypatch):
    store = install_memory_video_store(monkeypatch)
    upload = create_pending_upload()
    videos_svc.complete_upload(completion_request(upload))

    with pytest.raises(ValueError, match="source_key"):
        videos_svc.complete_upload(
            completion_request(upload, source_key=video_store.source_key("other"))
        )

    assert len(store.completed_multipart) == 1
    video = videos_svc.get_video(upload.video_id)
    assert video.status == VideoStatus.uploaded


async def test_video_responses_do_not_expose_pending_upload_id(monkeypatch, client):
    install_memory_video_store(monkeypatch)
    upload = create_pending_upload()

    detail_response = await client.get(f"/videos/{upload.video_id}")
    assert detail_response.status_code == 200
    assert "pending_upload_id" not in detail_response.json()

    list_response = await client.get("/videos")
    assert list_response.status_code == 200
    videos = list_response.json()
    assert len(videos) == 1
    assert "pending_upload_id" not in videos[0]
