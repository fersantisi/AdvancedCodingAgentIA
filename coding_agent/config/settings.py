"""Application settings, loaded from environment variables and an optional .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class SettingsError(Exception):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    tavily_api_key: str = ""
    command_timeout_seconds: float = 60.0
    max_tool_output_chars: int = 10_000
    max_read_file_chars: int = 50_000
    max_tool_iterations: int = 30
    llm_max_retries: int = 3
    log_file: Path = Path("agent.log")
    embeddings_model: str = "text-embedding-3-small"
    rag_store_path: Path = Path("rag_index.json")
    memory_file: Path = Path(".agent/memory.json")
    observability_provider: str = "none"
    compact_after_messages: int = 60
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    @classmethod
    def from_env(cls, env_file: Path | None = Path(".env")) -> Settings:
        """Build settings from the process environment, loading ``.env`` first."""
        if env_file is not None and env_file.exists():
            load_dotenv(env_file, override=False)
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", cls.llm_provider),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", cls.openai_model),
            tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
            command_timeout_seconds=_env_float(
                "COMMAND_TIMEOUT_SECONDS", cls.command_timeout_seconds
            ),
            max_tool_iterations=_env_int("MAX_TOOL_ITERATIONS", cls.max_tool_iterations),
            llm_max_retries=_env_int("LLM_MAX_RETRIES", cls.llm_max_retries),
            log_file=Path(os.getenv("AGENT_LOG_FILE", str(cls.log_file))),
            embeddings_model=os.getenv("EMBEDDINGS_MODEL", cls.embeddings_model),
            rag_store_path=Path(os.getenv("RAG_STORE_PATH", str(cls.rag_store_path))),
            memory_file=Path(os.getenv("AGENT_MEMORY_FILE", str(cls.memory_file))),
            observability_provider=os.getenv("OBSERVABILITY_PROVIDER", cls.observability_provider),
            compact_after_messages=_env_int("COMPACT_AFTER_MESSAGES", cls.compact_after_messages),
            langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            # LANGFUSE_HOST is canonical; LANGFUSE_BASE_URL is accepted as an alias
            # (the name the Langfuse SDK's own docs sometimes use).
            langfuse_host=(
                os.getenv("LANGFUSE_HOST")
                or os.getenv("LANGFUSE_BASE_URL")
                or cls.langfuse_host
            ),
        )

    def validate(self) -> None:
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise SettingsError(
                "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        if self.max_tool_iterations < 1:
            raise SettingsError("MAX_TOOL_ITERATIONS must be >= 1")
        if self.compact_after_messages < 10:
            raise SettingsError("COMPACT_AFTER_MESSAGES must be >= 10")
        if self.observability_provider == "langfuse" and not (
            self.langfuse_public_key and self.langfuse_secret_key
        ):
            raise SettingsError(
                "OBSERVABILITY_PROVIDER=langfuse requires LANGFUSE_PUBLIC_KEY and "
                "LANGFUSE_SECRET_KEY. Add them to your .env."
            )


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        raise SettingsError(f"{name} must be a number, got '{raw}'") from None


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise SettingsError(f"{name} must be an integer, got '{raw}'") from None
