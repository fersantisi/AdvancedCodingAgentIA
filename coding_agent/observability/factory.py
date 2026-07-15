"""Builds the configured tracer. New observability backends plug in here."""

from __future__ import annotations

from coding_agent.config.settings import Settings, SettingsError
from coding_agent.observability.base import NullTracer, Tracer


def create_tracer(settings: Settings) -> Tracer:
    """Instantiate the observability backend selected in settings."""
    if settings.observability_provider in ("", "none"):
        return NullTracer()
    if settings.observability_provider == "langfuse":
        from coding_agent.observability.langfuse_tracer import LangfuseTracer

        return LangfuseTracer(settings)
    raise SettingsError(
        f"Unknown observability provider '{settings.observability_provider}'. "
        "Supported: none, langfuse"
    )
