from functools import lru_cache

from app.core.config import get_settings
from app.integrations.llm.base import LLMProvider, LLMUnavailableError
from app.integrations.llm.gemini import GeminiProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Build the configured provider, or fail loudly. There is no silent fallback."""
    settings = get_settings()
    if settings.llm_provider != "gemini":
        raise LLMUnavailableError(f"unsupported LLM_PROVIDER: {settings.llm_provider!r}")
    key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
    if not key:
        raise LLMUnavailableError("GEMINI_API_KEY is not configured")
    return GeminiProvider(
        api_key=key,
        model=settings.llm_model,
        base_url=settings.gemini_base_url,
        api_revision=settings.gemini_api_revision,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
