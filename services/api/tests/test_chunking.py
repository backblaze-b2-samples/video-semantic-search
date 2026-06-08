"""Unit tests for semantic chunking — pure logic, no B2 or providers."""

from app.service.transcript import chunk_transcript
from app.types import Transcript, TranscriptSegment


def _seg(start: float, end: float, text: str) -> TranscriptSegment:
    return TranscriptSegment(start=start, end=end, text=text)


def test_chunks_are_timestamp_aligned_and_ordered():
    segs = [_seg(i, i + 1, "word " * 60) for i in range(5)]  # ~300 chars each
    transcript = Transcript(video_id="vid", segments=segs)

    chunks = chunk_transcript(transcript)

    assert chunks
    assert chunks[0].start == 0.0
    assert chunks[-1].end == 5.0
    assert chunks[0].chunk_id == "vid:0"
    for chunk in chunks:
        assert chunk.video_id == "vid"
        assert chunk.end >= chunk.start
        assert chunk.text


def test_empty_transcript_yields_no_chunks():
    assert chunk_transcript(Transcript(video_id="vid", segments=[])) == []
