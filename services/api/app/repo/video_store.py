"""B2 data access for the video namespace: presigned multipart uploads,
JSON artifact I/O, scoped listing, presigned playback, and tree deletion.

All objects live under `settings.video_prefix` so the bucket can be shared
with other samples. Per-video tree:

    videos/{video_id}/source.{ext}    original upload (multi-GB, multipart)
    videos/{video_id}/audio.m4a       extracted audio
    videos/{video_id}/transcript.json segments with timestamps
    videos/{video_id}/embeddings.json the search index (vectors + text)
    videos/{video_id}/meta.json       title, duration, status
    videos/{video_id}/clips/...       optional exported clips
"""

import json
import logging

from botocore.exceptions import ClientError

from app.config import settings
from app.repo.b2_client import get_s3_client

logger = logging.getLogger(__name__)


# --- Key layout -------------------------------------------------------------


def _base(video_id: str) -> str:
    return f"{settings.video_prefix}videos/{video_id}/"


def source_key(video_id: str, ext: str = "mp4") -> str:
    ext = (ext or "mp4").lstrip(".")
    return f"{_base(video_id)}source.{ext}"


def audio_key(video_id: str) -> str:
    return f"{_base(video_id)}audio.m4a"


def transcript_key(video_id: str) -> str:
    return f"{_base(video_id)}transcript.json"


def embeddings_key(video_id: str) -> str:
    return f"{_base(video_id)}embeddings.json"


def meta_key(video_id: str) -> str:
    return f"{_base(video_id)}meta.json"


# --- Presigned multipart upload (browser -> B2 direct) ----------------------


def create_multipart(key: str, content_type: str) -> str:
    client = get_s3_client()
    try:
        resp = client.create_multipart_upload(
            Bucket=settings.b2_bucket_name, Key=key, ContentType=content_type
        )
    except ClientError as e:
        raise RuntimeError(f"B2 create_multipart failed for '{key}': {e}") from e
    return resp["UploadId"]


def presign_part(
    key: str, upload_id: str, part_number: int, expires_in: int = 3600
) -> str:
    client = get_s3_client()
    try:
        return client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": settings.b2_bucket_name,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=expires_in,
        )
    except ClientError as e:
        raise RuntimeError(f"B2 presign_part failed for '{key}': {e}") from e


def complete_multipart(key: str, upload_id: str, parts: list[dict]) -> None:
    """Finalize a multipart upload. `parts` is [{"PartNumber", "ETag"}]."""
    client = get_s3_client()
    ordered = sorted(parts, key=lambda p: p["PartNumber"])
    try:
        client.complete_multipart_upload(
            Bucket=settings.b2_bucket_name,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": ordered},
        )
    except ClientError as e:
        raise RuntimeError(f"B2 complete_multipart failed for '{key}': {e}") from e


def abort_multipart(key: str, upload_id: str) -> None:
    client = get_s3_client()
    try:
        client.abort_multipart_upload(
            Bucket=settings.b2_bucket_name, Key=key, UploadId=upload_id
        )
    except ClientError as e:
        logger.warning("B2 abort_multipart failed for '%s': %s", key, e)


# --- JSON artifacts ---------------------------------------------------------


def put_json(key: str, payload: dict) -> None:
    client = get_s3_client()
    body = json.dumps(payload).encode("utf-8")
    try:
        client.put_object(
            Bucket=settings.b2_bucket_name,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
    except ClientError as e:
        raise RuntimeError(f"B2 put_json failed for '{key}': {e}") from e


def get_json(key: str) -> dict | None:
    client = get_s3_client()
    try:
        resp = client.get_object(Bucket=settings.b2_bucket_name, Key=key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey"):
            return None
        raise RuntimeError(f"B2 get_json failed for '{key}': {e}") from e
    return json.loads(resp["Body"].read())


# --- Listing / playback / delete --------------------------------------------


def list_video_ids() -> list[str]:
    """Return the id of every video under the sample prefix (scoped listing)."""
    client = get_s3_client()
    prefix = f"{settings.video_prefix}videos/"
    ids: list[str] = []
    token: str | None = None
    while True:
        kwargs: dict = {
            "Bucket": settings.b2_bucket_name,
            "Prefix": prefix,
            "Delimiter": "/",
        }
        if token:
            kwargs["ContinuationToken"] = token
        try:
            resp = client.list_objects_v2(**kwargs)
        except ClientError as e:
            raise RuntimeError(f"B2 list_video_ids failed: {e}") from e
        for cp in resp.get("CommonPrefixes", []):
            sub = cp["Prefix"][len(prefix) :].rstrip("/")
            if sub:
                ids.append(sub)
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return ids


def playback_url(key: str, expires_in: int = 3600) -> str:
    """Presigned GET URL for inline playback (seek the source by media fragment)."""
    client = get_s3_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.b2_bucket_name, "Key": key},
            ExpiresIn=expires_in,
        )
    except ClientError as e:
        raise RuntimeError(f"B2 playback_url failed for '{key}': {e}") from e


def delete_video_tree(video_id: str) -> int:
    """Batch-delete every object under videos/{video_id}/. Returns count."""
    client = get_s3_client()
    prefix = _base(video_id)
    deleted = 0
    token: str | None = None
    while True:
        kwargs: dict = {"Bucket": settings.b2_bucket_name, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        try:
            resp = client.list_objects_v2(**kwargs)
        except ClientError as e:
            raise RuntimeError(f"B2 list-for-delete failed: {e}") from e
        objects = [{"Key": o["Key"]} for o in resp.get("Contents", [])]
        if objects:
            try:
                client.delete_objects(
                    Bucket=settings.b2_bucket_name, Delete={"Objects": objects}
                )
            except ClientError as e:
                raise RuntimeError(f"B2 delete_objects failed: {e}") from e
            deleted += len(objects)
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return deleted
