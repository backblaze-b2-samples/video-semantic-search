<!-- last_verified: 2026-06-05 -->
# Feature: Transcription

## Purpose
Turn an ingested video's audio into a timestamped transcript with Whisper, and persist it to B2 as `transcript.json`.

## Used By
- Pipeline: `services/api/app/service/ingest.py` (runs after upload completes)
- API (indirectly): `POST /videos/uploads/complete` schedules the pipeline; `POST /videos/{id}/reindex` re-runs it

## Core Functions
- `services/api/app/repo/media.py` — `download_to_temp()`, `extract_audio()` (ffmpeg → mono 16 kHz), `probe_duration()` (ffprobe)
- `services/api/app/repo/transcription.py` — `is_configured()`, `transcribe()` → `_transcribe_openai()` (Whisper) / `_transcribe_local()` (faster-whisper, not yet wired)
- `services/api/app/types/transcript.py` — `Transcript`, `TranscriptSegment`

## Inputs
- A video already uploaded to B2 (`source.{ext}`)
- `OPENAI_API_KEY` (default provider) or `TRANSCRIPTION_PROVIDER=local`

## Outputs
- `transcript.json` in B2: `{ video_id, language, duration_seconds, segments: [{start, end, text}] }`
- `meta.json` status transitions: `extracting → transcribing → chunking → embedding → ready`

## Flow
1. Download `source.{ext}` from B2 to a temp file.
2. `ffmpeg` extracts a mono 16 kHz audio track; `ffprobe` reads duration.
3. Whisper (`audio.transcriptions`, `verbose_json`, segment timestamps) returns segments.
4. The transcript is written to B2 and handed to chunking (see [Semantic Search](semantic-search.md)).

## Providers & degradation
- Provider SDKs import **lazily**; the module loads with no key installed.
- `transcribe()` raises `ProviderNotConfiguredError` when nothing is configured; the pipeline catches it and leaves the video at `uploaded` with a clear note — no crash.
- Default: OpenAI Whisper. Alternative: local `faster-whisper` (`TRANSCRIPTION_PROVIDER=local`) — adapter stub present, wiring deferred (see tech-debt tracker).

## Edge Cases
- ffmpeg missing → pipeline marks the video `failed` with the ffmpeg error; `pnpm doctor` warns up front.
- Very long videos → transcription runs in a background task (no queue); see [RELIABILITY.md](../RELIABILITY.md).

## Verification
- `pnpm test:api` (provider guard test: `transcribe()` raises when unconfigured)
- Manual (with `OPENAI_API_KEY` + ffmpeg): ingest a short clip; confirm `transcript.json` appears and status reaches `ready`.

## Related Docs
- [Video Ingest](video-ingest.md) · [Semantic Search](semantic-search.md) · [ARCHITECTURE.md](../../ARCHITECTURE.md)
