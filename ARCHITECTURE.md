<!-- last_verified: 2026-06-05 -->
# Architecture

## Components

- **apps/web/** — Next.js 16 frontend (App Router, Tailwind v4, shadcn/ui)
  - Dashboard with video-centric stats (videos indexed, minutes transcribed, chunks embedded) + B2 activity chart
  - **Library** — sample-scoped explorer of ingested videos with pipeline status; "Add video" opens the multipart ingest dialog
  - **Search** — natural-language question → ranked timestamped clips, played inline; optional synthesized answer
  - **Upload** + **Files** (bucket explorer) — kept from the starter kit
- **services/api/** — FastAPI backend (strict layered architecture)
  - Presigned multipart upload orchestration (browser → B2 direct)
  - Ingest pipeline: audio extraction (ffmpeg) → transcription (Whisper) → chunking → embeddings → index persisted to B2
  - Semantic search: query embedding + in-process NumPy cosine over the B2-stored index
  - Health, metrics, structured JSON logging, structural tests
- **packages/shared/** — TypeScript types mirroring the API's Pydantic models

## Backend layering

```
types/     Pydantic models — no logic, no imports from other layers
  |
config/    Settings (pydantic-settings) — depends only on types
  |
repo/      Data access + external adapters (boto3, OpenAI, Anthropic, ffmpeg)
  |
service/   Business logic — calls repo, returns types
  |
runtime/   FastAPI routes — calls service, never repo directly
```

### Layering rules

1. Dependencies flow downward only: `types → config → repo → service → runtime`
2. No backward imports.
3. **External SDKs only in `repo/`** — `boto3`, `openai`, `anthropic`, `faster_whisper`. (NumPy is a math library, not an external-service SDK, and is used for cosine similarity in `service/`.)
4. All boundary data uses Pydantic models.
5. Each file stays under 300 lines.

### Directory structure (backend)

```
services/api/app/
  types/        video.py, transcript.py, search.py, files.py, stats.py, upload.py
  config/       settings.py (B2_* + provider keys + pipeline knobs)
  repo/         b2_client.py, video_store.py, media.py (ffmpeg),
                transcription.py, embeddings.py, llm.py, errors.py
  service/      videos.py, ingest.py, transcript.py (chunking), search.py,
                files.py, upload.py, metadata.py
  runtime/      videos.py, search.py, files.py, upload.py, health.py, metrics.py
```

## Data stores

- **Backblaze B2** — the sole data store, including the search index. No application database.
  - Per-video tree under `video-semantic-search/videos/{video_id}/`: `source.{ext}`, `audio.m4a`, `transcript.json`, `embeddings.json` (the index), `meta.json` (status), `clips/…` (optional).
  - `meta.json` carries the pipeline status, so the Library reflects progress with no separate state store.

## External services

- **Backblaze B2 S3 API** — storage, retrieval, deletion, presigned URLs (multipart + GET).
- **OpenAI** — Whisper transcription + text embeddings (`repo/transcription.py`, `repo/embeddings.py`).
- **Anthropic (Claude)** — optional answer synthesis over retrieved clips (`repo/llm.py`).
- **ffmpeg/ffprobe** — local audio extraction + duration probing (`repo/media.py`).

Provider adapters import their SDKs **lazily** and expose `is_configured()`. With no keys set, the app still imports and runs; the pipeline degrades to "uploaded, awaiting provider" and search returns a clear not-configured state.

## Data flows

- **Ingest**: Browser → `POST /videos/uploads` (API opens `create_multipart_upload`, returns presigned part URLs) → browser PUTs each part directly to B2 → `POST /videos/uploads/complete` (API completes the upload, schedules the pipeline as a `BackgroundTask`).
- **Pipeline** (`service/ingest.py`): download source → ffmpeg audio → Whisper transcript (→ B2) → semantic chunks → embeddings → `EmbeddingIndex` (→ B2) → status `ready`. Status persisted at each stage.
- **Search**: Browser → `POST /search` → embed query → load `embeddings.json` for ready videos from B2 → NumPy cosine top-k → map chunks to timestamped `Clip`s with presigned playback URLs → optional Claude synthesis.
- **Playback**: `<video src="{presigned}#t=start,end">` seeks the source in B2 — no clip files generated.

## Boundary invariants

- **External SDK containment** — verified by `tests/test_structure.py::test_external_sdks_only_in_repo`.
- **No raw dicts at boundaries** — typed Pydantic models everywhere.
- **No mutable cross-layer globals**.
- **Validated inputs** — FastAPI/Pydantic at the boundary; file keys validated against traversal.

## Deployment

- **Local dev** — `pnpm dev` runs both services via `concurrently` (web `:3000`, api `:8000`).
- **Railway** — two services from one repo (see `infra/railway/README.md`). The ingest pipeline runs in-process as a background task (no external queue) — see [docs/RELIABILITY.md](docs/RELIABILITY.md).

## Canonical files

- Presigned multipart + B2 artifact I/O: `services/api/app/repo/video_store.py`
- Ingest pipeline: `services/api/app/service/ingest.py`
- Search: `services/api/app/service/search.py`
- B2 S3 client (user-agent + region): `services/api/app/repo/b2_client.py`
- Frontend multipart upload: `apps/web/src/lib/api-client.ts` (`ingestVideo`)
- Data hooks: `apps/web/src/lib/queries.ts`
- Structural tests: `services/api/tests/test_structure.py`

## References

- [docs/SECURITY.md](docs/SECURITY.md) · [docs/RELIABILITY.md](docs/RELIABILITY.md) · [AGENTS.md](AGENTS.md)
