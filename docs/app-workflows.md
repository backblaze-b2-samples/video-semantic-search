<!-- last_verified: 2026-06-05 -->
# App Workflows

User journeys inside the application.

## Ingest a Video

- User opens `/library` and clicks **Add video**.
- Drops/selects a video; the browser uploads it to B2 in parts (presigned multipart) with a progress bar — multi-GB files are fine.
- On completion the API finalizes the upload and starts the pipeline; the video appears in the Library and its status advances (`uploaded → extracting → transcribing → chunking → embedding → ready`), polling live.
- See: [Video Ingest](features/video-ingest.md), [Transcription](features/transcription.md)

## Search the Video(s)

- User navigates to `/search` and asks a natural-language question (⌘/Ctrl+Enter to submit).
- Optionally toggles **Synthesize an answer (Claude)**.
- Results come back as ranked **timestamped clips**; each plays inline by seeking the source video. If synthesis was on, a short cited answer appears above the clips.
- If no provider is configured, or no video is indexed yet, a clear guidance state is shown instead of empty results.
- See: [Semantic Search](features/semantic-search.md)

## Manage the Library

- `/library` lists every ingested video with status, length, chunk count, size, and date.
- **Re-index** re-runs the pipeline for a video; **Delete** (with confirm) removes the video and all its derived data from B2.
- See: [Video Library](features/video-library.md)

## View Dashboard

- `/` shows video metrics — videos indexed, minutes transcribed, chunks embedded, storage used — plus a B2 upload-activity chart and a recent-videos table.
- The page polls while videos are processing so the numbers update live.
- See: [Dashboard](features/dashboard.md)

## Browse the Bucket / Generic Upload (kept from the starter kit)

- `/files` is the full-bucket explorer: tree view, preview, download, delete. See: [File Browser](features/file-browser.md)
- `/upload` is the generic small-file uploader (proxied through the API, ≤100 MB) for transcripts, posters, and other small assets. See: [File Upload](features/file-upload.md)
