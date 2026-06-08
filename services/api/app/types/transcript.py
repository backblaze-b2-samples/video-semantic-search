from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    start: float  # seconds from the start of the video
    end: float
    text: str


class Transcript(BaseModel):
    """Full transcript for a video. Persisted to B2 as transcript.json."""

    video_id: str
    language: str | None = None
    duration_seconds: float | None = None
    segments: list[TranscriptSegment]


class Chunk(BaseModel):
    """A semantic window over one or more transcript segments."""

    chunk_id: str
    video_id: str
    start: float
    end: float
    text: str


class ChunkEmbedding(BaseModel):
    chunk_id: str
    start: float
    end: float
    text: str
    vector: list[float]


class EmbeddingIndex(BaseModel):
    """The per-video vector index. Persisted to B2 as embeddings.json — this
    is the search index, so B2 stays the sole data store (no vector DB)."""

    video_id: str
    model: str
    dim: int
    chunks: list[ChunkEmbedding]
