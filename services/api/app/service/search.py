"""Search service — embed the question, score it against each video's
embedding index (loaded from B2) with in-process numpy cosine similarity, and
return the best timestamped clips. Optionally synthesizes an answer with Claude.

The index lives in B2 (embeddings.json per video), so B2 stays the sole data
store — there is no vector database."""

import logging

import numpy as np

from app.repo import embeddings, llm, video_store
from app.service import videos as videos_svc
from app.types import Clip, EmbeddingIndex, SearchRequest, SearchResponse, VideoStatus

logger = logging.getLogger(__name__)


def _cosine(query: np.ndarray, vector: list[float]) -> float:
    vec = np.asarray(vector, dtype="float32")
    denom = float(np.linalg.norm(query) * np.linalg.norm(vec))
    if denom == 0.0:
        return 0.0
    return float(np.dot(query, vec) / denom)


def search(req: SearchRequest) -> SearchResponse:
    question = req.question.strip()
    if not question:
        raise ValueError("Question must not be empty")

    # No embedding provider → return a clear "not configured" state, not a 500.
    if not embeddings.is_configured():
        return SearchResponse(
            question=question, clips=[], answer=None, provider_configured=False
        )

    videos_by_id = {v.video_id: v for v in videos_svc.list_videos()}
    if req.video_id:
        target_ids = [req.video_id] if req.video_id in videos_by_id else []
    else:
        target_ids = [
            vid
            for vid, v in videos_by_id.items()
            if v.status == VideoStatus.ready
        ]

    indexes: list[EmbeddingIndex] = []
    for vid in target_ids:
        data = video_store.get_json(video_store.embeddings_key(vid))
        if data and data.get("chunks"):
            indexes.append(EmbeddingIndex(**data))
    if not indexes:
        return SearchResponse(
            question=question, clips=[], answer=None, provider_configured=True
        )

    query = np.asarray(embeddings.embed_query(question), dtype="float32")
    scored = [
        (_cosine(query, ch.vector), index.video_id, ch)
        for index in indexes
        for ch in index.chunks
    ]
    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[: max(1, req.top_k)]

    playback_cache: dict[str, str | None] = {}
    clips: list[Clip] = []
    for score, vid, ch in top:
        video = videos_by_id.get(vid)
        if vid not in playback_cache:
            playback_cache[vid] = _playback(video.source_key if video else None)
        clips.append(
            Clip(
                video_id=vid,
                title=video.title if video else vid,
                start=ch.start,
                end=ch.end,
                text=ch.text,
                score=round(float(score), 4),
                playback_url=playback_cache[vid],
            )
        )

    answer = _synthesize(question, clips) if req.synthesize else None
    return SearchResponse(
        question=question, clips=clips, answer=answer, provider_configured=True
    )


def _playback(source_key: str | None) -> str | None:
    if not source_key:
        return None
    try:
        return video_store.playback_url(source_key)
    except RuntimeError:
        return None


def _synthesize(question: str, clips: list[Clip]) -> str | None:
    if not (clips and llm.is_configured()):
        return None
    try:
        return llm.synthesize_answer(question, [c.text for c in clips])
    except Exception:
        logger.warning("Answer synthesis failed", exc_info=True)
        return None
