"""Tests for search + provider guards. Hermetic: no keys are set in the test
environment, so these exercise the graceful-degradation paths without touching
B2 or any provider."""

import numpy as np
import pytest

from app.repo import ProviderNotConfiguredError, embeddings, llm, transcription
from app.service.search import _cosine, search
from app.types import SearchRequest


def test_embeddings_require_key():
    with pytest.raises(ProviderNotConfiguredError):
        embeddings.embed_query("hello")


def test_transcription_requires_provider():
    with pytest.raises(ProviderNotConfiguredError):
        transcription.transcribe("/tmp/does-not-exist.m4a")


def test_answer_synthesis_requires_key():
    with pytest.raises(ProviderNotConfiguredError):
        llm.synthesize_answer("q", ["snippet"])


def test_search_rejects_empty_question():
    with pytest.raises(ValueError, match="empty"):
        search(SearchRequest(question="   "))


def test_search_without_provider_degrades_gracefully():
    resp = search(SearchRequest(question="what is discussed?"))
    assert resp.provider_configured is False
    assert resp.clips == []
    assert resp.answer is None


def test_cosine_similarity_bounds():
    a = np.asarray([1.0, 0.0, 1.0], dtype="float32")
    assert _cosine(a, [1.0, 0.0, 1.0]) == pytest.approx(1.0)
    assert _cosine(a, [0.0, 1.0, 0.0]) == pytest.approx(0.0)
    zero = np.asarray([0.0, 0.0], dtype="float32")
    assert _cosine(zero, [1.0, 2.0]) == 0.0
