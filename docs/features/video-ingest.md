<!-- last_verified: 2026-06-25 -->
# Feature: Video Ingest

## Purpose
Upload a (potentially multi-GB) video straight to Backblaze B2 using a presigned **S3 multipart** upload — the browser PUTs parts directly to B2, so the API never buffers the bytes — then finalize and kick off the transcription/embedding pipeline.

## Used By
- UI: `/library` page → "Add video" (`apps/web/src/components/library/ingest-dialog.tsx`)
- API: `POST /videos/uploads`, `POST /videos/uploads/complete`

## Core Functions
- `apps/web/src/lib/api-client.ts` — `ingestVideo()` (orchestrates create → PUT parts → complete), `putPart()`
- `apps/web/src/lib/queries.ts` — `useIngestVideo()`
- `services/api/app/runtime/videos.py` — `create_upload_endpoint`, `complete_upload_endpoint`
- `services/api/app/service/videos.py` — `create_upload()`, `complete_upload()`
- `services/api/app/repo/video_store.py` — `create_multipart()`, `presign_part()`, `complete_multipart()`, `abort_multipart()`

## Inputs
- `CreateUploadRequest`: `filename`, `size_bytes`, `content_type`
- `CompleteUploadRequest`: `video_id`, `source_key`, `upload_id`, `title`, `size_bytes`, `content_type`, `parts[]` (`part_number`, `etag`)

## Outputs
- `POST /videos/uploads` → `MultipartUpload` (`upload_id`, `source_key`, `part_size`, presigned `parts[]`)
- `POST /videos/uploads/complete` → `Video` (status `uploaded`); schedules `ingest.run_pipeline` as a background task
- Side effect: `source.{ext}` written to B2 under `video-semantic-search/videos/{video_id}/`

## Flow
1. Browser asks the API to open an upload. The API calls `create_multipart_upload`, computes the number of parts from `size_bytes / multipart_part_size` (64 MB default), presigns an `upload_part` URL per part, and writes an initial `meta.json` (status `uploading`).
2. Browser slices the file and PUTs each part directly to the presigned B2 URL, reading the returned `ETag` and tracking progress.
3. Browser calls `/videos/uploads/complete` with the part ETags. The API calls `complete_multipart_upload`, sets status `uploaded`, and schedules the pipeline.

## B2 / CORS requirements
Because the browser PUTs to B2 directly, the **bucket CORS policy** must allow `PUT` from the web origin and **expose the `ETag` response header** (`Access-Control-Expose-Headers: ETag`) — without it the browser can't read the ETag and the upload can't complete. Playback also needs `GET` allowed.

## Edge Cases
- File exceeds `MAX_VIDEO_SIZE` (5 GB default) → `400`.
- Completion requires an existing pending upload for the submitted `video_id`,
  and the submitted `source_key` and `upload_id` must match that pending
  upload's saved metadata; mismatches are rejected before multipart completion
  or metadata mutation. Legacy pending metadata without persisted
  `pending_upload_id` can still complete when the saved `source_key` matches.
- A part PUT fails / no ETag exposed → the client surfaces an `ApiError`; call `abort_multipart_upload` to clean up (server-side helper available).
- Provider keys absent → upload still succeeds; the pipeline leaves the video at `uploaded` with a "configure provider" note (see [Transcription](transcription.md)).

## Verification
- `pnpm lint && pnpm lint:api && pnpm test:api && pnpm check:structure`
- Mocked pipeline round-trip:
  `cd services/api && python -m pytest tests/test_ingest_pipeline_integration.py::test_ingest_pipeline_persists_artifacts_and_searches_with_mocked_providers`
- Optional live provider-pipeline smoke check with a vetted fixture in `services/api/tests/fixtures/live-ingest/` (also checks synthesized answers when `ANTHROPIC_API_KEY` is set):
  `cd services/api && RUN_LIVE_INGEST_TEST=1 LIVE_INGEST_VIDEO_PATH="$PWD/tests/fixtures/live-ingest/provider-smoke.mp4" python -m pytest tests/test_live_provider_pipeline_smoke.py::test_live_provider_pipeline_smoke_against_uploaded_source`
- Manual: add a small `.mp4` from the Library; confirm `source.{ext}` + `meta.json` appear under the video's prefix in the bucket (visible in the Files explorer).

## Related Docs
- [Transcription](transcription.md) · [Video Library](video-library.md) · [ARCHITECTURE.md](../../ARCHITECTURE.md)
