"""Semantic chunking — group consecutive transcript segments into
~paragraph-sized, timestamp-aligned chunks for embedding. Pure logic, no SDKs."""

from app.types import Chunk, Transcript, TranscriptSegment

# Rough proxy for "a paragraph". Kept char-based to avoid a tokenizer dep;
# embedding models tolerate this granularity well.
_MAX_CHARS = 1000


def chunk_transcript(transcript: Transcript) -> list[Chunk]:
    groups: list[list[TranscriptSegment]] = []
    current: list[TranscriptSegment] = []
    length = 0
    for seg in transcript.segments:
        current.append(seg)
        length += len(seg.text)
        if length >= _MAX_CHARS:
            groups.append(current)
            current = []
            length = 0
    if current:
        groups.append(current)

    chunks: list[Chunk] = []
    for idx, group in enumerate(groups):
        text = " ".join(s.text for s in group).strip()
        if not text:
            continue
        chunks.append(
            Chunk(
                chunk_id=f"{transcript.video_id}:{idx}",
                video_id=transcript.video_id,
                start=group[0].start,
                end=group[-1].end,
                text=text,
            )
        )
    return chunks
