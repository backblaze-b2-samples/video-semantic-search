<!-- last_verified: 2026-06-05 -->
# Feature: Metadata Extraction

## Purpose
Extract metadata from files uploaded via the generic `/upload` path and return it alongside the upload result.

## Used By
- API: `POST /upload` (called after the B2 write)
- UI: upload results, `apps/web/src/components/files/file-metadata-panel.tsx`

## Core Functions
- `services/api/app/service/metadata.py` — `extract_metadata()`, `_extract_image_metadata()`

## Inputs
- `file_data: bytes`, `filename: str`, `content_type: str`

## Outputs
- `FileMetadataDetail`: filename, size, mime type, extension, MD5, SHA-256, uploaded-at
- Image-specific (optional): `image_width`, `image_height`, `exif`

## Flow
- Compute MD5 + SHA-256.
- If the content type is an image → extract dimensions + EXIF via Pillow.
- Return `FileMetadataDetail`.

## Scope notes (changed from the starter kit)
- **PDF extraction was removed** — this sample has no PDF use case, so the `PyPDF2` dependency and the PDF branch are gone. The `pdf_*` fields remain on the generic detail model but are always unset here.
- **Audio/video** duration is **not** computed on the generic upload path. For ingested videos it's derived during the pipeline with `ffprobe` (`services/api/app/repo/media.py`) and stored in the video's `meta.json` — see [Transcription](transcription.md).

## Edge Cases
- Corrupt image → Pillow fails silently; image fields stay null.
- Unknown content type → only common fields (hashes, size, extension) populated.

## Verification
- `pnpm test:api` · `pnpm lint:api`

## Related Docs
- [File Upload](file-upload.md) · [Transcription](transcription.md) · [ARCHITECTURE.md](../../ARCHITECTURE.md)
