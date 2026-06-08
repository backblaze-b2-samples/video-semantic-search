"""Embedding adapter. Provider SDK imported lazily."""

from app.config import settings
from app.repo.errors import ProviderNotConfiguredError


def is_configured() -> bool:
    return bool(settings.openai_api_key)


def model_name() -> str:
    return settings.embedding_model


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not is_configured():
        raise ProviderNotConfiguredError(
            "Embeddings require OPENAI_API_KEY (model: "
            f"{settings.embedding_model})."
        )
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.embeddings.create(model=settings.embedding_model, input=texts)
    return [d.embedding for d in resp.data]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
