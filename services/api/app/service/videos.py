"""Video service — ingest orchestration (presigned multipart) and library
listing/status/deletion. Business logic only; all B2 I/O via the repo layer."""

import math
import re
import secrets
from datetime import UTC, datetime

from app.config import settings
from app.repo import video_store
from app.types import (
    CompleteUploadRequest,
    CreateUploadRequest,
    MultipartUpload,
    PresignedPart,
    Video,
    VideoStatus,
)
from app.types.formatting import humanize_bytes

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class VideoNotFoundError(Exception):
    def __init__(self, detail: str = "Video not found"):
        self.detail = detail
        super().__init__(detail)


def _slug(filename: str) -> str:
    base = filename.rsplit("/", 1)[-1]
    if "." in base:
        base = base.rsplit(".", 1)[0]
    base = _SLUG_RE.sub("-", base.lower()).strip("-")
    return base[:48] or "video"


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"


def _load(video_id: str) -> Video | None:
    data = video_store.get_json(video_store.meta_key(video_id))
    return Video(**data) if data else None


def _save(video: Video) -> None:
    video_store.put_json(
        video_store.meta_key(video.video_id), video.model_dump(mode="json")
    )


def create_upload(req: CreateUploadRequest) -> MultipartUpload:
    """Open a presigned multipart upload (browser PUTs parts directly to B2)."""
    if req.size_bytes <= 0:
        raise ValueError("size_bytes must be positive")
    if req.size_bytes > settings.max_video_size:
        raise ValueError(
            f"Video exceeds the max size of {humanize_bytes(settings.max_video_size)}"
        )

    video_id = f"{_slug(req.filename)}-{secrets.token_hex(3)}"
    key = video_store.source_key(video_id, _ext(req.filename))
    upload_id = video_store.create_multipart(key, req.content_type)

    part_size = settings.multipart_part_size
    num_parts = max(1, math.ceil(req.size_bytes / part_size))
    parts = [
        PresignedPart(
            part_number=n, url=video_store.presign_part(key, upload_id, n)
        )
        for n in range(1, num_parts + 1)
    ]

    # Record the pending upload so it appears in the Library immediately.
    _save(
        Video(
            video_id=video_id,
            title=req.filename,
            status=VideoStatus.uploading,
            source_key=key,
            size_bytes=req.size_bytes,
            size_human=humanize_bytes(req.size_bytes),
            content_type=req.content_type,
            created_at=datetime.now(UTC),
        )
    )
    return MultipartUpload(
        video_id=video_id,
        source_key=key,
        upload_id=upload_id,
        part_size=part_size,
        parts=parts,
    )


def complete_upload(req: CompleteUploadRequest) -> Video:
    """Finalize the multipart upload. The runtime layer schedules the pipeline."""
    parts = [{"PartNumber": p.part_number, "ETag": p.etag} for p in req.parts]
    video_store.complete_multipart(req.source_key, req.upload_id, parts)

    video = _load(req.video_id) or Video(
        video_id=req.video_id,
        title=req.title,
        status=VideoStatus.uploaded,
        source_key=req.source_key,
        size_bytes=req.size_bytes,
        size_human=humanize_bytes(req.size_bytes),
        content_type=req.content_type,
        created_at=datetime.now(UTC),
    )
    video.status = VideoStatus.uploaded
    video.error = None
    _save(video)
    return video


def list_videos() -> list[Video]:
    videos = [v for vid in video_store.list_video_ids() if (v := _load(vid))]
    videos.sort(key=lambda v: v.created_at, reverse=True)
    return videos


def get_video(video_id: str) -> Video:
    video = _load(video_id)
    if not video:
        raise VideoNotFoundError()
    return video


def try_get(video_id: str) -> Video | None:
    return _load(video_id)


def playback_url(video_id: str) -> str:
    return video_store.playback_url(get_video(video_id).source_key)


def delete_video(video_id: str) -> int:
    return video_store.delete_video_tree(video_id)


def update_status(
    video_id: str,
    status: VideoStatus,
    *,
    error: str | None = None,
    duration_seconds: float | None = None,
    chunk_count: int | None = None,
) -> None:
    """Persist a pipeline state transition to meta.json (best effort)."""
    video = _load(video_id)
    if not video:
        return
    video.status = status
    video.error = error
    if duration_seconds is not None:
        video.duration_seconds = duration_seconds
    if chunk_count is not None:
        video.chunk_count = chunk_count
    _save(video)
