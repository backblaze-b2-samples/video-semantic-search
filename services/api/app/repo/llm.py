"""Answer-synthesis adapter (Claude). Optional — search works without it.
SDK imported lazily."""

from app.config import settings
from app.repo.errors import ProviderNotConfiguredError

_PROMPT = (
    "Answer the question using only the numbered transcript excerpts below. "
    "Cite excerpts inline like [1]. Keep it to a few sentences. If the "
    "excerpts do not contain the answer, say so plainly.\n\n"
    "Question: {question}\n\nExcerpts:\n{context}"
)


def is_configured() -> bool:
    return bool(settings.anthropic_api_key)


def synthesize_answer(question: str, snippets: list[str]) -> str:
    if not is_configured():
        raise ProviderNotConfiguredError(
            "Answer synthesis requires ANTHROPIC_API_KEY."
        )
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    context = "\n\n".join(f"[{i + 1}] {s}" for i, s in enumerate(snippets))
    message = client.messages.create(
        model=settings.answer_model,
        max_tokens=400,
        messages=[
            {
                "role": "user",
                "content": _PROMPT.format(question=question, context=context),
            }
        ],
    )
    parts = [
        block.text
        for block in message.content
        if getattr(block, "type", None) == "text"
    ]
    return "".join(parts).strip()
