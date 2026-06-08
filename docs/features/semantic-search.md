<!-- last_verified: 2026-06-05 -->
# Feature: Semantic Search

## Purpose
Answer a natural-language question by finding the transcript moments most similar to it, and return them as **timestamped clips** that play inline. The vector index lives in B2 — there is no vector database.

## Used By
- UI: `/search` page (`apps/web/src/app/search/page.tsx`, `apps/web/src/components/search/clip-card.tsx`)
- API: `POST /search`

## Core Functions
- `apps/web/src/lib/queries.ts` — `useSearch()`
- `services/api/app/runtime/search.py` — `search_endpoint`
- `services/api/app/service/search.py` — `search()`, `_cosine()` (NumPy)
- `services/api/app/service/transcript.py` — `chunk_transcript()` (chunking, ~1000 chars, timestamp-aligned)
- `services/api/app/repo/embeddings.py` — `embed_query()`, `embed_texts()`
- `services/api/app/repo/llm.py` — `synthesize_answer()` (optional, Claude)
- `services/api/app/repo/video_store.py` — `get_json()` (load `embeddings.json`), `playback_url()`

## Inputs
- `SearchRequest`: `question`, optional `video_id` (scope), `top_k` (default 5), `synthesize` (bool)

## Outputs
- `SearchResponse`: `question`, `clips[]` (`video_id`, `title`, `start`, `end`, `text`, `score`, `playback_url`), `answer` (string | null), `provider_configured` (bool)

## Flow (indexing, during ingest)
Chunk the transcript into ~paragraph windows aligned to segment timestamps → embed each chunk → write `EmbeddingIndex` (`{video_id, model, dim, chunks:[{chunk_id, start, end, text, vector}]}`) to B2 as `embeddings.json`.

## Flow (query)
1. If no embedding provider is configured → return `provider_configured: false` (UI shows a "configure a provider" state). No B2 calls.
2. Embed the question. Load `embeddings.json` for the targeted ready videos from B2.
3. Score every chunk by cosine similarity (in-process NumPy), take the top-k.
4. Build `Clip`s with a presigned playback URL per source. Optionally synthesize an answer over the top clips with Claude.
5. The UI plays each clip by setting `<video src="{playback_url}#t=start,end">` — a media fragment seeks the source; no clip files are generated.

## Edge Cases
- No `OPENAI_API_KEY` → `provider_configured: false`.
- No ready videos / empty index → empty `clips`, with a "no matching moments" empty state.
- Empty question → `400`.
- Synthesis requested but `ANTHROPIC_API_KEY` absent or the call fails → `answer` is `null`; clips still return.

## Verification
- `pnpm test:api` (`test_video_search.py`: cosine bounds, empty-question rejection, graceful degradation without keys)
- Manual: ingest + index a video, ask a question, confirm clips return and play at the right timestamp.

## Related Docs
- [Transcription](transcription.md) · [Video Library](video-library.md) · [ARCHITECTURE.md](../../ARCHITECTURE.md)
