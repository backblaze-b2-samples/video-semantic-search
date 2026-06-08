<!-- last_verified: 2026-04-22 -->
# Security

Security principles and implementation for the video-semantic-search.

## Trust Boundaries

- **Frontend -> API**: CORS-restricted to configured origins, scoped to `GET/POST/DELETE/OPTIONS`
- **API -> B2**: Authenticated via `B2_APPLICATION_KEY_ID` + `B2_APPLICATION_KEY`, signature v4
- **Client -> B2 (download)**: Presigned `GET` URLs (short expiry, `Content-Disposition: attachment`)
- **Client -> B2 (large upload)**: Presigned multipart `PUT` URLs — the browser uploads parts directly; the API never sees the bytes
- **API -> providers**: OpenAI (Whisper + embeddings) and Anthropic (optional synthesis), called only from `repo/` adapters

## Upload Validation

- Filename sanitization: path traversal, null bytes, unsafe chars stripped
- MIME/extension consistency check against allowlist
- Chunked streaming with size enforcement (100MB default)
- Content-type allowlist (images, PDFs, text, archives, audio/video)
- Empty file rejection

## File Key Validation

- Empty keys rejected
- Path traversal patterns rejected (`../`, `%2e%2e`, backslashes, null bytes)
- The bucket is the only access boundary — add prefix scoping in
  `services/api/app/service/files.py::validate_key` if your deployment
  shares a bucket with other workloads

## Download Safety

- Download presigned URLs force `Content-Disposition: attachment`
- Prevents inline rendering of user-uploaded content (XSS mitigation)

## Presigned Multipart Upload & CORS

- Large video uploads go **browser → B2 directly** via presigned multipart `PUT` URLs; the API only mints URLs and finalizes the upload.
- This requires the bucket's CORS policy to allow `PUT`/`GET` from the web origin and to **expose the `ETag` header** (the browser needs it to complete the upload). Scope CORS to your real origins in production.
- Presigned URLs are time-limited capability tokens — don't log them.

## Playback

- Inline playback uses presigned `GET` URLs with a media fragment (`#t=start,end`) against the source object. This intentionally allows inline rendering — it's the user's own ingested video — unlike the attachment-forced download path.

## AI Provider Keys

- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` are read via pydantic-settings, used only inside `repo/` adapters, and never exposed to the browser.
- Transcript text is sent to the configured providers for embedding/answer synthesis — call this out in any privacy review.

## Secrets Management

- All secrets loaded via environment variables (pydantic-settings)
- Never committed to source control
- `.env.example` documents required variables without values

## Agent Security Rules

- Never commit `.env`, credentials, or API keys
- Never weaken validation without explicit instruction
- Never bypass CORS, auth, or input sanitization
- Always validate at system boundaries
