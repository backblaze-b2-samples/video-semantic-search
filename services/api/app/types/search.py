from pydantic import BaseModel


class SearchRequest(BaseModel):
    question: str
    # None = search across every ready video; otherwise scope to one.
    video_id: str | None = None
    top_k: int = 5
    # When true and an answer model is configured, synthesize a short answer
    # over the retrieved clips with Claude.
    synthesize: bool = False


class Clip(BaseModel):
    """A timestamped moment that answers the question, playable inline."""

    video_id: str
    title: str
    start: float
    end: float
    text: str
    score: float
    playback_url: str | None = None


class SearchResponse(BaseModel):
    question: str
    clips: list[Clip]
    answer: str | None = None
    # False when no provider/index is available — the UI shows a clear
    # "configure a provider and ingest a video" state instead of empty results.
    provider_configured: bool = True
