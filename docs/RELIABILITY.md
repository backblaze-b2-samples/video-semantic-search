<!-- last_verified: 2026-03-06 -->
# Reliability

Reliability expectations and practices for this project.

## Health Checks

- `GET /health` verifies B2 connectivity and returns `healthy` or `degraded`
- Health endpoint is always available, even when B2 is down

## Error Handling

- HTTP handlers return structured error responses with appropriate status codes
- External service failures (B2) are caught and surfaced as 500/503 responses
- No unhandled exceptions leak stack traces to clients

## Logging

- Structured JSON logging via Python stdlib
- Every request gets a `request_id` for tracing
- Log levels: ERROR for failures, WARNING for degraded state, INFO for requests

## Observability

- Request timing middleware logs duration for every request
- `/metrics` endpoint exposes basic Prometheus-format counters
- Upload success/failure counts tracked

## Graceful Degradation

- File listing returns empty list (not error) when B2 has no objects
- Metadata extraction failures don't block upload (return partial metadata)
- Frontend shows skeleton states while loading, error states on failure
- AI provider not configured → video upload still succeeds; the pipeline records a "configure provider" note and search returns `provider_configured: false` instead of erroring

## Ingest Pipeline

- Transcription/embedding runs as an in-process FastAPI **BackgroundTask** — there is no external job queue (a deliberate demo simplification; see [tech-debt-tracker](exec-plans/tech-debt-tracker.md)).
- Status is persisted to each video's `meta.json` in B2 at every stage, so the Library reflects progress and survives page reloads.
- **In-flight pipelines are lost if the API restarts.** Recover by re-indexing the affected video (Library "Re-index" / `POST /videos/{id}/reindex`); it's idempotent — it overwrites the derived artifacts.
- The pipeline never crashes the worker: provider-not-configured leaves the video at `uploaded`; any other failure marks it `failed` with the error recorded in `meta.json`.

## Deployment

- Railway health checks on `/health`
- Zero-downtime deploys via rolling updates
- Environment-specific configuration via env vars (no config files in prod)
