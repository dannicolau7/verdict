"""Verdict configuration module.

Settings are loaded from environment variables and/or a .env file in the working directory.

Override via .env file:
    Create a `.env` file next to your project root:
        ANTHROPIC_API_KEY=sk-ant-...
        DEFAULT_JUDGE_MODEL=claude-opus-4-6
        MAX_CONCURRENT_EXECUTIONS=10

Override via direct env vars (takes precedence over .env):
    $ ANTHROPIC_API_KEY=sk-ant-... verdict eval --target my_agent.py

Override in tests (cache_clear pattern):
    def test_something(monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("MAX_CONCURRENT_EXECUTIONS", "1")
        get_settings.cache_clear()          # discard the cached instance
        s = get_settings()                  # fresh Settings from the patched env
        ...
        get_settings.cache_clear()          # clean up after the test

Why SecretStr for API keys:
    pydantic.SecretStr masks the value in repr(), __str__(), and model serialization.
    Accessing the raw key requires an explicit .get_secret_value() call, making
    accidental leaks in logs, tracebacks, or error messages much harder.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Required                                                             #
    # ------------------------------------------------------------------ #

    anthropic_api_key: SecretStr
    """Anthropic API key. Required. Never logged — accessed via .get_secret_value()."""

    # ------------------------------------------------------------------ #
    # Model selection (defaults — all overridable via env)                #
    # ------------------------------------------------------------------ #

    default_generator_model: str = "claude-sonnet-4-6"
    """Model used by the Test Generator agent to produce adversarial prompts."""

    default_executor_model: str = "claude-haiku-4-5-20251001"
    """Model used by the Executor agent to run prompts against the target system."""

    default_judge_model: str = "claude-sonnet-4-6"
    """Model used by the Judge agent to evaluate target system responses."""

    default_reporter_model: str = "claude-sonnet-4-6"
    """Model used by the Reporter agent to produce the EvalReport."""

    # ------------------------------------------------------------------ #
    # Concurrency and timeouts                                             #
    # ------------------------------------------------------------------ #

    max_concurrent_executions: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of target-system executions running simultaneously.",
    )

    default_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=600,
        description="Per-execution timeout in seconds. Exceeded calls raise TimeoutError.",
    )

    # ------------------------------------------------------------------ #
    # Paths                                                                #
    # ------------------------------------------------------------------ #

    reports_dir: Path = Path("./reports")
    """Directory where EvalReport JSON and Markdown files are written."""

    # ------------------------------------------------------------------ #
    # Logging                                                              #
    # ------------------------------------------------------------------ #

    log_level: str = "INFO"
    """Python logging level string: DEBUG, INFO, WARNING, ERROR, CRITICAL."""

    # ------------------------------------------------------------------ #
    # Optional integrations                                                #
    # ------------------------------------------------------------------ #

    langsmith_api_key: SecretStr | None = None
    """LangSmith API key for tracing. Optional."""

    langsmith_project: str = "verdict"
    """LangSmith project name to associate traces with."""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached global Settings instance.

    Uses lru_cache so Settings is parsed from the environment exactly once.
    Call ``get_settings.cache_clear()`` in tests to force re-instantiation.
    """
    return Settings()
