<!-- last_verified: 2026-06-05 -->
# Feature: Video Library

## Purpose
A **sample-scoped** explorer (distinct from the full-bucket Files explorer) that lists the videos this app has ingested — under the `video-semantic-search/videos/` prefix — with each video's pipeline status, and lets you add, re-index, or delete one.

## Used By
- UI: `/library` page (`apps/web/src/app/library/page.tsx`), `components/library/{video-list,status-badge,ingest-dialog}.tsx`
- API: `GET /videos`, `GET /videos/{id}`, `POST /videos/{id}/reindex`, `DELETE /videos/{id}`

## Core Functions
- `apps/web/src/lib/queries.ts` — `useVideos()` (polls every 4s while any video is mid-pipeline), `useReindexVideo()`, `useDeleteVideo()`
- `services/api/app/runtime/videos.py` — list / get / reindex / delete handlers
- `services/api/app/service/videos.py` — `list_videos()`, `get_video()`, `delete_video()`, `update_status()`
- `services/api/app/repo/video_store.py` — `list_video_ids()` (scoped `list_objects_v2`), `delete_video_tree()` (`delete_objects`)

## Inputs / Outputs
- `GET /videos` → `Video[]` (newest first), each read from its `meta.json`
- `DELETE /videos/{id}` → `{ deleted, video_id, objects }` — removes the whole `videos/{id}/` tree from B2
- `POST /videos/{id}/reindex` → `Video` and re-schedules the pipeline

## Flow
- The page lists videos with a status badge (`uploading → extracting → transcribing → chunking → embedding → ready` / `failed`), length, chunk count, size, and date.
- While anything is processing, the list polls so progress updates live (status is read from each `meta.json`).
- "Add video" opens the multipart [Ingest](video-ingest.md) dialog. Re-index re-runs the pipeline; Delete confirms via an AlertDialog, then drops the video's entire B2 tree.

## Why a scoped explorer (in addition to Files)
The Files page browses the *entire* bucket (kept from the starter kit). The Library is scoped to *this app's* videos and is status-aware — it's the management surface for the pipeline.

## Edge Cases
- Empty → "No videos yet" empty state prompting an upload.
- API unreachable → inline `ErrorState` with retry.
- `failed` videos show their error inline and can be re-indexed.

## Verification
- `pnpm lint && pnpm build` (frontend), `pnpm test:api && pnpm check:structure` (backend)
- Manual: ingest a video, watch the status advance, then delete it and confirm the tree is gone from the Files explorer.

## Related Docs
- [Video Ingest](video-ingest.md) · [File Browser](file-browser.md) · [ARCHITECTURE.md](../../ARCHITECTURE.md)
