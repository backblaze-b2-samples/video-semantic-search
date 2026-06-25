# Live Ingest Fixtures

Place one approved small speech-video fixture in this directory when running
the opt-in live provider smoke test.

Requirements:
- File must stay local and uncommitted.
- File must be 25 MiB or smaller.
- File extension must be `.mp4`, `.m4v`, `.mov`, or `.webm`.
- File must be safe to upload to B2 and send to configured AI providers.

Example:

```bash
cp ~/approved-fixtures/provider-smoke.mp4 services/api/tests/fixtures/live-ingest/
cd services/api
RUN_LIVE_INGEST_TEST=1 \
LIVE_INGEST_VIDEO_PATH="$PWD/tests/fixtures/live-ingest/provider-smoke.mp4" \
python -m pytest tests/test_ingest_pipeline_integration.py::test_live_provider_pipeline_smoke_against_uploaded_source
```
