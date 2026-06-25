import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.service import ingest
from app.service.videos import (
    VideoNotFoundError,
    complete_upload,
    create_upload,
    delete_video,
    get_video,
    list_videos,
    playback_url,
)
from app.types import CompleteUploadRequest, CreateUploadRequest, MultipartUpload, Video

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/videos", response_model=list[Video])
async def list_videos_endpoint():
    return list_videos()


@router.post("/videos/uploads", response_model=MultipartUpload)
async def create_upload_endpoint(req: CreateUploadRequest):
    try:
        return create_upload(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/videos/uploads/complete", response_model=Video)
async def complete_upload_endpoint(req: CompleteUploadRequest, background_tasks: BackgroundTasks):
    try:
        completion = complete_upload(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    if completion.start_pipeline:
        # Kick the transcription/embedding pipeline off the request path.
        background_tasks.add_task(ingest.run_pipeline, completion.video.video_id)
        logger.info("Video upload completed: video_id=%s", completion.video.video_id)
    return completion.video


@router.get("/videos/{video_id}", response_model=Video)
async def get_video_endpoint(video_id: str):
    try:
        return get_video(video_id)
    except VideoNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None


@router.get("/videos/{video_id}/playback")
async def playback_endpoint(video_id: str):
    try:
        return {"url": playback_url(video_id)}
    except VideoNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None


@router.post("/videos/{video_id}/reindex", response_model=Video)
async def reindex_endpoint(video_id: str, background_tasks: BackgroundTasks):
    try:
        video = get_video(video_id)
    except VideoNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    background_tasks.add_task(ingest.run_pipeline, video_id)
    return video


@router.delete("/videos/{video_id}")
async def delete_video_endpoint(video_id: str):
    deleted = delete_video(video_id)
    logger.info("Video deleted: video_id=%s objects=%d", video_id, deleted)
    return {"deleted": True, "video_id": video_id, "objects": deleted}
