"""Builds the configured LLM client. New providers plug in here."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent.config.settings import Settings, SettingsError
from coding_agent.llm.base import LLMClient
from coding_agent.llm.openai_client import OpenAIClient
from coding_agent.llm.retry import RetryingLLMClient

if TYPE_CHECKING:
    from coding_agent.observability.base import Tracer


def create_llm_client(settings: Settings, tracer: Tracer | None = None) -> LLMClient:
    """Instantiate the provider selected in settings, wrapped with tracing and retries.

    Tracing sits inside the retry wrapper so every attempt (including failed
    ones) is recorded by the observability backend.
    """
    if settings.llm_provider == "openai":
        client: LLMClient = OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
    else:
        raise SettingsError(
            f"Unknown LLM provider '{settings.llm_provider}'. Supported: openai"
        )
    if tracer is not None:
        # Imported here, not at module level: observability's tracing client
        # subclasses llm.base, so a top-level import would be circular.
        from coding_agent.observability.tracing_client import TracingLLMClient

        client = TracingLLMClient(client, tracer, settings.openai_model)
    return RetryingLLMClient(client, max_attempts=settings.llm_max_retries)
