# Scaffold plan — `video-semantic-search`

**Source of truth:** `.claude/scratch/vcsk-7e2a08fa-5dd0-47fe-9bb4-3bc60c6ebc5e/` (fresh clone of `vibe-coding-starter-kit`).
**Target:** `./video-semantic-search` (under `sampleapps/.local/`).
**Standards:** parent `../CLAUDE.md` — S3 API default, custom user-agent on every S3 client, standardized `B2_*` env var names.

---

## Decisions to confirm before build

These change what gets built — please confirm or adjust at approval.

- **D0 — Starter-kit (boto3) vs Genblaze packages.** You invoked `/new-b2-sample`, which builds **from `vibe-coding-starter-kit`** (B2 accessed via `boto3`, contained in the `repo/` layer). Your concept's "Suggested stack" mentions `genblaze-s3`. This plan uses the **starter-kit / boto3** path (it's a Next.js + FastAPI B2 stack and meets all three standards). If you actually want the genblaze-package variant, stop here and run `/new-genblaze-sample` instead.
- **D1 — Upload mechanism for multi-GB video.** Answering the concept's open question: **presigned S3 multipart upload, browser → B2 direct** (not proxied through the API, not single-shot). The API never buffers GBs; the browser PUTs parts to presigned URLs with progress + resumability. Single-shot presigned PUT is the documented fallback for small assets. The existing `/upload` page is **kept as-is** as the starter's generic small-file surface; the large-video path is a new **Ingest** flow.
- **D2 — Transcription + embeddings provider.** Default to **provider APIs**: OpenAI **Whisper** (`audio.transcriptions`) for transcription + OpenAI **text-embedding-3-small** for embeddings, both behind swappable `repo/` adapters. Lowest install friction, no GPU/model download. Documented alternative: local `faster-whisper` + `sentence-transformers` (no API key, heavier deps). Answer synthesis over retrieved clips (optional enhancement) uses **Claude (`claude-sonnet-4-6`)**.
- **D3 — Vector store.** Answering the concept's open question: **in-process**, no sidecar, no DB. Embeddings persist as a JSON file in B2 per video; at query time they're loaded from B2 and scored with numpy cosine similarity. **B2 stays the sole data store** (preserves the starter's "no application database" invariant).
- **D4 — `user_agent_extra` / UTM content tag.** Normally sourced from the board sub-issue's `user_agent_extra` field; none was provided here. Proposed value: **`b2ai-video-semantic-search`** (used for both the S3 client user-agent and the README/sidebar `utm_content`). Confirm or supply the canonical tag.
- **D5 — Single multi-modal flow vs split pages.** Answering the concept's open question: **one ingest pipeline, surfaced across focused pages** — Ingest (add video), Library (scoped explorer + per-video status/transcript), Search (ask → timestamped clips). Not split into separate video/audio/transcript apps.

---

## 1. Purpose

**Video Semantic Search** turns long-form video into a searchable, timestamped knowledge base. You upload a multi-GB video (lecture, podcast, webinar, recorded call, YouTube export); the app extracts audio, transcribes it with Whisper, splits the transcript into semantic chunks, and embeds them. You then ask natural-language questions and get back the exact moments that answer them — each result is a timestamped clip you play inline by seeking the source video.

Backblaze **B2 is the system of record for every heavy artifact**: the source video, the extracted audio, the transcript JSON, the embedding vectors, and any exported clips. It exercises B2's **write path at scale** (presigned multipart ingest of multi-GB files, browser → B2 direct) and its **read path at scale** (repeated presigned-URL reads for playback). It's for podcast/YouTube creators, researchers, and teams sitting on hours of video who want "chat with your video" / "AI video search" without standing up a separate vector database — B2 holds everything, including the index.

---

## 2. Architecture delta vs `vibe-coding-starter-kit`

The starter kit is the ceiling. Keep its full B2-backed scaffolding; strip the little this app doesn't need; add the video pipeline + scoped library + search surfaces.

### KEEP (as-is)
| Area | What | Why |
|---|---|---|
| UI kit | `apps/web/src/components/ui/**`, design tokens in `globals.css`, `/design` page + `components/design/**` | Starter contract — never edit generated `ui/`; restyle via tokens |
| Layout | `app-sidebar.tsx`, `header.tsx`, `theme-provider.tsx`, `health-banner.tsx`, `command-palette.tsx` | Reused chrome (nav + palette get **new entries**, not replacement) |
| **Bucket explorer** | **`/files` route, `app/files/`, `components/files/**`, `lib/file-tree.ts`** | **NON-NEGOTIABLE KEEP** — full-bucket browse stays |
| Generic upload | `/upload` route, `app/upload/`, `components/upload/**`, `runtime/upload.py`, `service/upload.py` | Starter's reusable small-file B2 surface (transcripts/posters/small assets). Large video uses the new Ingest flow (D1) |
| Layered API | `types/ → config/ → repo/ → service/ → runtime/`, `main.py`, `health.py`, `metrics.py`, JSON logging, `/health`, `/metrics` | Architecture invariants + observability |
| Data layer | `lib/api-client.ts`, `lib/queries.ts`, `lib/query-client.tsx`, `lib/refresh-context.tsx` | Extend (new hooks), don't replace. No bare `useEffect+fetch` |
| Settings / states | `/settings`, `danger-zone.tsx`, `error.tsx`, `loading.tsx`, `not-found.tsx`, `global-error.tsx` | Adapt copy only |
| Tooling | `scripts/dev.sh`, `doctor.mjs`, `pick-port.mjs`, pnpm workspace, `tsconfig`, eslint, `playwright.config`, `.pre-commit-config.yaml` | Generic quality gates (doctor gets new checks) |
| Shared types | `packages/shared/src/types.ts` | Extend with video/transcript/search models |
| Docs scaffold | `docs/` tree, `ARCHITECTURE.md`, `SECURITY.md`, `RELIABILITY.md`, `app-workflows.md`, `dev-workflows.md`, `exec-plans/` | Rewrite content (§5), keep structure + same-PR doc discipline |
| Structural tests | `tests/test_structure.py` (+ generalize SDK-containment, see Add) | Mechanical enforcement |

### TRIM (remove from starter)
| Remove | Why |
|---|---|
| `CODE_REVIEW.md` (root) | Stale code-review report of the starter kit itself; irrelevant to this sample |
| `docs/images/b2-starterkit-dashboard1.png`, `b2-starterkit-fileview2.png` | Starter screenshots; misleading for a video app. README "what it looks like" → "screenshots pending" placeholder; real shots added later via `sample-screenshotter` (binary-asset creation is gated — not done in scaffold) |
| `docs/exec-plans/completed/2026-02-*.md`, `2026-02-13-*`, `2026-02-14-*` | The starter kit's own build history; confuses agents about *this* sample's provenance. Reset `tech-debt-tracker.md` to this sample's debt |
| PDF metadata path: `PyPDF2` dep + `_extract_pdf_metadata()` in `service/metadata.py` | No PDFs in a video app. Repurpose metadata extraction toward **audio/video** (duration/codec/bitrate via `ffprobe`) — the doc already lists these as optional A/V fields. Keep image/hash extraction (poster/thumbnail) |

*Everything else in the starter is lean enough to keep. Next.js default svgs in `public/` are left untouched (no value in churning them).*

### ADD (new for `video-semantic-search`)
**Frontend**
- Nav + palette entries: **Library** (`/library`), **Search** (`/search`). (Ingest is reached from Library / "Add video".)
- **Library page** (`/library`) — **sample-scoped asset explorer** (NON-NEGOTIABLE add): lists videos under the sample's own prefix with status (`uploaded → extracting → transcribing → chunking → embedding → ready` / `failed`), duration, size, ingest date; row → per-video detail (transcript view, re-index, delete). "Add video" → Ingest dialog.
- **Ingest flow** — presigned **multipart** upload (browser → B2 direct) with per-part progress, then "complete" handshake that kicks off the pipeline (D1).
- **Search page** (`/search`) — question input → ranked **timestamped clips**; inline `<video>` seeking the source via presigned URL + media-fragment (`#t=start,end`); optional Claude-synthesized answer that cites clips.
- **Dashboard adaptation** (`/`, `components/dashboard/**`) — per AGENTS.md §2 the dashboard is the adapt surface: stat cards → *Videos indexed*, *Minutes transcribed*, *Chunks embedded*, *Storage used*; chart → ingests (or searches) over time; recent table → recently ingested videos with status badge. Same `runtime→service→repo` layering + TanStack Query hooks.

**Backend (`services/api/app/`)** — all external SDKs stay in `repo/`
- `repo/b2_client.py` (+): multipart (`create_multipart_upload`, presigned `upload_part` URLs, `complete_multipart_upload`, `abort_multipart_upload`), batch `delete_objects` (drop a whole `videos/{id}/` tree), prefix-scoped listing, get/put JSON helpers (transcript / embeddings / meta).
- `repo/transcription.py` — Whisper adapter (OpenAI default; local `faster-whisper` alt).
- `repo/embeddings.py` — embedding adapter (OpenAI `text-embedding-3-small` default).
- `repo/llm.py` *(optional)* — Claude (`claude-sonnet-4-6`) answer-synthesis adapter.
- `service/ingest.py` — orchestrates: create/complete upload → `ffmpeg` audio extract → transcribe → semantic-chunk → embed → persist artifacts to B2 → update `meta.json` status.
- `service/search.py` — embed query, load video embeddings from B2, numpy cosine top-k, map chunks → timestamped clips, optional synthesis.
- `service/transcript.py` — semantic chunking of transcript segments (token/overlap windows aligned to segment timestamps).
- `runtime/videos.py` — `POST /videos/uploads` (create multipart), `POST /videos/uploads/{id}/complete`, `GET /videos`, `GET /videos/{id}`, `GET /videos/{id}/status`, `DELETE /videos/{id}`, `GET /videos/{id}/playback` (presigned source URL).
- `runtime/search.py` — `POST /search` (question → clips [+ answer]).
- `types/video.py`, `types/transcript.py`, `types/search.py` — Pydantic models.
- Generalize structural SDK-containment test from "boto3 only in repo/" → "external SDKs (`boto3`, `openai`, `anthropic`, `faster_whisper`) only in `repo/`".

**Shared TS types** (`packages/shared/src/types.ts`): `Video`, `VideoStatus`, `TranscriptSegment`, `Chunk`, `SearchResult` / `Clip`, `MultipartUpload`.

**B2 key layout** (one bucket, namespaced so it can be shared):
```
video-semantic-search/
  videos/{video_id}/source.{ext}        # original upload (multi-GB, presigned multipart)
  videos/{video_id}/audio.m4a           # extracted audio (ffmpeg)
  videos/{video_id}/transcript.json     # segments with start/end timestamps
  videos/{video_id}/embeddings.json     # chunk vectors + text + timestamps (the index)
  videos/{video_id}/meta.json           # title, duration, status, sizes
  videos/{video_id}/clips/{start}-{end}.mp4   # optional exported clips (write-path demo)
```
`video_id = {filename-slug}-{shortid}`.

**System prerequisite:** `ffmpeg` (audio extraction; optional clip export) — add a `doctor.mjs` check.

**New env vars** (see §3 / §6): standards fixes `B2_APPLICATION_KEY_ID`, `B2_REGION`; plus `OPENAI_API_KEY`, optional `ANTHROPIC_API_KEY`, `VIDEO_PREFIX` (default `video-semantic-search/`), `MAX_VIDEO_SIZE`, provider/model knobs.

---

## 3. B2 surface (S3 operations)

All S3-compatible — **no b2-native API**, so standard #1 holds with nothing to flag.

| Path | S3 ops |
|---|---|
| **Write** | `create_multipart_upload`, presigned `upload_part`, `complete_multipart_upload`, `abort_multipart_upload` (video ingest); `put_object` (audio, transcript, embeddings, meta, exported clips; generic `/upload`) |
| **Read** | `list_objects_v2` (bucket explorer + prefix-scoped library), `head_object` (metadata), `generate_presigned_url`/`get_object` (playback-by-seek, clip/asset download, preview) — repeated reads for playback = read-at-scale |
| **Delete** | `delete_object`, `delete_objects` (batch-drop a video's derived tree) |
| **Connectivity** | `head_bucket` (`/health`) |

**Standards compliance:**
1. S3 default — yes, all via `boto3` S3, contained in `repo/`. No b2-native. ✅
2. Custom user-agent — single `get_s3_client()` sets `user_agent_extra`; change `b2ai-oss-start` → **`b2ai-video-semantic-search`** (D4). ✅
3. `B2_*` names — **fix the starter's deviation** (known; the `b2-doctor` skill is stale on this): rename `B2_KEY_ID` → `B2_APPLICATION_KEY_ID` and **add `B2_REGION`** (used as boto3 `region_name`). Keep `B2_APPLICATION_KEY`, `B2_BUCKET_NAME`, `B2_ENDPOINT`. Touch: `config/settings.py` (`b2_key_id`→`b2_application_key_id`, add `b2_region`), `repo/b2_client.py`, `main.py` `REQUIRED_B2_SETTINGS` + placeholder set, `.env.example`, `README.md`, `scripts/doctor.mjs`. ✅

---

## 4. Key features (seed README list + `docs/features/*` stubs)

1. **Video ingest** — multi-GB presigned multipart upload, browser → B2 direct, with progress.
2. **Transcription** — Whisper turns audio into timestamped transcript segments stored in B2.
3. **Semantic search** — ask in natural language; embeddings + cosine retrieval return the moments that answer it.
4. **Timestamped clips** — results play inline by seeking the source video (presigned URL + media fragments); optional clip export to B2.
5. **Video Library** — sample-scoped explorer showing each video's pipeline status and transcript.
6. **Bucket explorer** *(kept)* — full-bucket browse of every B2 object.

---

## 5. Doc transforms

| Starter doc | Action |
|---|---|
| `README.md` | **Rewrite** — H1 "Video Semantic Search", value prop, "screenshots pending" placeholder, feature list (§4), quick start (add `ffmpeg` + provider keys + standards `B2_*`), tech stack (+ Whisper/embeddings/Claude), commands, doc map; refresh UTM `utm_content=b2ai-video-semantic-search` |
| `ARCHITECTURE.md` | **Rewrite** — add transcription/embeddings/search components; data flows (ingest pipeline, search); external services (B2 + OpenAI + optional Anthropic); B2 sole-store incl. index; generalize SDK-containment invariant; new canonical files |
| `AGENTS.md` | **Update** — repo map; §2 building-on contract reframed to this app (keep Files/Upload, add Library/Search); invariants ("external SDKs only in `repo/`"); commands; doc map. Keep layering rules |
| `docs/features/file-upload.md` | **Keep** (generic upload still exists), minor note pointing to video-ingest |
| `docs/features/file-browser.md` | **Keep** (bucket explorer), light edit |
| `docs/features/dashboard.md` | **Rewrite** for new metrics |
| `docs/features/metadata-extraction.md` | **Rewrite** — drop PDF, redirect to audio/video (`ffprobe`) + poster/thumbnail |
| `docs/features/_template.md` | Keep |
| **New** `docs/features/video-ingest.md` | Presigned multipart + pipeline kickoff |
| **New** `docs/features/transcription.md` | Whisper provider, transcript JSON shape |
| **New** `docs/features/semantic-search.md` | Chunking, embeddings, retrieval, clip mapping, optional synthesis |
| **New** `docs/features/video-library.md` | Scoped explorer + per-video status |
| `docs/app-workflows.md`, `dev-workflows.md`, `SECURITY.md`, `RELIABILITY.md` | Update for large uploads, presigned URLs, provider-key handling, `ffmpeg`, playback |
| `docs/exec-plans/completed/2026-02-*` | **Delete** (starter history). This plan → `completed/initial-scaffold.md` at finalize. Reset `tech-debt-tracker.md` |

---

## 6. Rename table

| Kind | From | To |
|---|---|---|
| Repo / dir | `vibe-coding-starter-kit` | `video-semantic-search` |
| Root pkg `name` | `vibe-coding-starter-kit` | `video-semantic-search` |
| npm scope (web) | `@vibe-coding-starter-kit/web` | `@video-semantic-search/web` |
| npm scope (shared) | `@vibe-coding-starter-kit/shared` | `@video-semantic-search/shared` |
| pkg refs | root `package.json` `--filter` scripts; `apps/web/package.json` dep; `lib/queries.ts` import; README `pnpm --filter …` e2e cmd; `pnpm-lock.yaml` (regenerate) | new scopes |
| Title Case | "Vibe Coding Starter Kit" / "OSS Starter Kit" | "Video Semantic Search" |
| Sidebar header text | `OSS Starter Kit` (`app-sidebar.tsx`) | `Video Semantic Search` |
| FastAPI `title` | `OSS Starter Kit API` (`main.py`) | `Video Semantic Search API` |
| FastAPI `description` | "File upload and management API…" | video-semantic-search description |
| user-agent + UTM content | `b2ai-oss-start` (`b2_client.py`, `app-sidebar.tsx` footer, README links, SECURITY.md) | `b2ai-video-semantic-search` (D4) |
| Env var | `B2_KEY_ID` | `B2_APPLICATION_KEY_ID` (+ add `B2_REGION`) |
| Settings field | `b2_key_id` | `b2_application_key_id` (+ add `b2_region`) |
| Doc image refs | `b2-starterkit-*.png` | removed / "screenshots pending" |
| Image tags | — | N/A (no Dockerfile present) |
| Workflow slugs | — | N/A (no `.github/workflows`) |

---

## Build scope (this scaffold) vs implemented-later

To keep the deliverable reviewable and honest:

**Builder produces now (must compile, lint, pass structural tests, run):**
- Full rename + working starter surfaces (Upload, Files/bucket-explorer, Dashboard, `/health`, `/metrics`, B2).
- Standards fixes (B2_* names + region, user-agent).
- New nav/pages: Library + Search render; Ingest dialog present.
- New API modules (`videos.py`, `search.py`) + `repo/`/`service/` adapters + `types/` + shared TS types, wired through api-client/queries — typed, with the **presigned multipart + B2 artifact I/O implemented for real** (mechanical boto3), and the **ML steps (Whisper / embeddings / cosine / synthesis / ffmpeg) behind adapters that are structured + documented but may be stubbed** (clearly marked TODO returning typed placeholders) so the tree builds without provider keys.
- All docs rewritten/stubbed per §5; structural tests green (incl. generalized SDK-containment).

**Implemented later (documented in feature docs + an exec-plan; this is "the first feature" from Phase 5):**
- End-to-end pipeline: real Whisper transcription, real embeddings, real cosine retrieval, optional Claude synthesis, optional `ffmpeg` clip export.

The app must degrade gracefully without provider keys (generic starter features keep working; video features surface a clear "configure provider" state rather than crashing).
