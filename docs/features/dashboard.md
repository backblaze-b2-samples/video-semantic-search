<!-- last_verified: 2026-06-05 -->
# Feature: Dashboard

## Purpose
Give an at-a-glance overview of the video search index: how many videos are indexed, how much has been transcribed, how many chunks are embedded, and overall B2 storage/activity.

## Used By
- UI: `/` page (`apps/web/src/app/page.tsx`)
- API: `GET /videos`, `GET /files/stats`, `GET /files/stats/activity`

## Core Functions
- `apps/web/src/components/dashboard/stats-cards.tsx` — derives video metrics from `useVideos()` + storage from `useFileStats()`
- `apps/web/src/components/dashboard/recent-videos-table.tsx` — most-recent videos with status badges
- `apps/web/src/components/dashboard/upload-chart.tsx` — B2 upload activity (last 7 days)
- `apps/web/src/lib/queries.ts` — `useVideos()`, `useFileStats()`, `useUploadActivity()`

## Inputs
- None (loads automatically)

## Outputs
- Stat cards: **Videos Indexed** (status `ready`), **Minutes Transcribed** (Σ `duration_seconds`/60), **Chunks Embedded** (Σ `chunk_count`), **Storage Used** (`/files/stats`)
- Recent Videos table: newest videos with title, status, length, added date (`GET /videos`)
- Upload activity chart: server-aggregated daily B2 upload counts (`GET /files/stats/activity`)

## Flow
- Page loads → `useVideos()` and `useFileStats()`/`useUploadActivity()` fetch in parallel.
- Video metrics are aggregated client-side over the `useVideos()` data (still through the TanStack Query hook — no bare `useEffect + fetch`).
- The videos query polls every 4s while any video is mid-pipeline, so the cards/table update live.

## Edge Cases
- API unreachable → cards/table surface an inline `ErrorState` (not misleading zeros).
- No videos yet → zeros + "No videos yet" empty state on the table.

## UX States
- Loading: skeletons. Empty: "No videos yet". Loaded: populated cards, chart, table.

## Verification
- `pnpm lint && pnpm build` (frontend)
- Manual: ingest a video; confirm the cards and recent-videos table update as it reaches `ready`.

## Related Docs
- [Video Library](video-library.md) · [Semantic Search](semantic-search.md) · [ARCHITECTURE.md](../../ARCHITECTURE.md)
