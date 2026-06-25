<!-- last_verified: 2026-06-25 -->
# Tech Debt Tracker

Known tech debt items. Agents update this when they discover or create tech debt.

| Description | Impact | Proposed Resolution | Priority | Status |
|---|---|---|---|---|
| Ingest pipeline implemented but not verified end-to-end against live providers | Whisper/embeddings/Claude live code paths remain unverified in default CI because provider credentials are not available. | `services/api/tests/test_ingest_pipeline_integration.py` covers the ingest artifact + search + synthesized answer round-trip with mocked providers and includes a bounded opt-in live B2/OpenAI smoke test with Claude synthesis when configured. Run that live test with an approved fixture before marking this covered. | High | Partially covered |
| Ingest runs as an in-process FastAPI `BackgroundTask` (no queue) | In-flight pipelines are lost on API restart; no retry/backoff; long jobs occupy a worker | Move to a real job queue (e.g. Redis/RQ, Celery) for production; document the demo limitation | Medium | Open |
| Local transcription (`faster-whisper`) adapter is a stub | `TRANSCRIPTION_PROVIDER=local` raises `NotImplementedError` | Wire `repo/transcription.py::_transcribe_local` + add `faster-whisper` to requirements | Medium | Open |
| Search loads every ready video's `embeddings.json` from B2 per query | O(all chunks) per search; extra B2 GETs at scale | Cache the index in-process (e.g. `lru_cache`) or precompute a combined index; fine for the demo | Low | Open |
| Clip export (ffmpeg-cut a segment → B2) is documented but not implemented | The write-path "generated clips" story is playback-by-seek only | Add a `repo/media.py::export_clip` + endpoint that writes `clips/{start}-{end}.mp4` | Low | Open |
| `pdf_*` fields remain on `FileMetadataDetail` though PDF extraction was removed | Dead optional fields | Drop the fields from the Pydantic + shared TS models and the metadata panel | Low | Open |
