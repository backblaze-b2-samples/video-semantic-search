class ProviderNotConfiguredError(RuntimeError):
    """Raised when an AI provider (transcription / embeddings / LLM) is needed
    but not configured. The service layer catches this and degrades gracefully
    rather than returning a 500."""
