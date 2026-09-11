"""Application configuration module using Pydantic Settings.

Manages environment variables, secrets, service endpoints, and operational
thresholds for TravelMate AI services and LangGraph agent pipelines.
"""

from __future__ import annotations

from typing import Annotated
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global application settings and environment variables.

    Attributes:
        openai_api_base: Base URL for OpenAI-compatible LLM endpoint (DeepSeek-V3).
        openai_api_key: Secret API key for primary LLM.
        llm_model: LLM model identifier.
        llm_max_tokens: Maximum tokens for generation.
        llm_temperature: Sampling temperature.
        anthropic_api_key: Optional fallback key for Anthropic Claude.
        anthropic_model: Fallback Claude model identifier.
        embedding_provider: Embedding service provider name.
        embedding_model: Hugging Face model identifier for multilingual E5.
        embedding_dimension: Output dimension of embedding vector (768).
        hf_api_key_1: Primary Hugging Face user access token.
        hf_api_key_2: Secondary Hugging Face user access token for rotation.
        hf_rotation_cooldown_seconds: Penalty cooldown duration on HTTP 429.
        hf_request_timeout_seconds: HTTP client timeout for inference requests.
        database_url: Async SQLAlchemy connection string for PostgreSQL.
        redis_url: Connection URL for Redis session store and cache.
        redis_session_ttl: Session state expiry in seconds (default: 30 minutes).
        langfuse_secret_key: Secret key for Langfuse observability.
        langfuse_public_key: Public key for Langfuse observability.
        langfuse_host: Host endpoint for Langfuse server.
        app_env: Deployment environment (development, staging, production).
        app_debug: Debug mode flag.
        bot_version: Version identifier of the TravelMate bot.
        system_prompt_version: Active system prompt identifier.
        log_level: Logging verbosity level.
        rate_limit_per_minute: Maximum requests allowed per IP per minute.
        cors_origins: Allowed origins for CORS middleware.
        api_secret_key: Secret key used for internal signing or auth tokens.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === LLM Engine (DeepSeek-V3 Primary) ===
    openai_api_base: str = Field(
        default="https://api.deepseek.com/v1",
        alias="OPENAI_API_BASE",
    )
    openai_api_key: str = Field(
        default="",
        alias="OPENAI_API_KEY",
    )
    llm_model: str = Field(
        default="deepseek-chat",
        alias="LLM_MODEL",
    )
    llm_max_tokens: int = Field(
        default=4096,
        alias="LLM_MAX_TOKENS",
    )
    llm_temperature: float = Field(
        default=0.2,
        alias="LLM_TEMPERATURE",
    )

    # Optional Fallback LLM (Claude)
    anthropic_api_key: str | None = Field(
        default=None,
        alias="ANTHROPIC_API_KEY",
    )
    anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        alias="ANTHROPIC_MODEL",
    )

    # === Embedding Service (Hugging Face Serverless) ===
    embedding_provider: str = Field(
        default="huggingface",
        alias="EMBEDDING_PROVIDER",
    )
    embedding_model: str = Field(
        default="intfloat/multilingual-e5-base",
        alias="EMBEDDING_MODEL",
    )
    embedding_dimension: int = Field(
        default=768,
        alias="EMBEDDING_DIMENSION",
    )
    hf_api_key_1: str = Field(
        default="",
        alias="HF_API_KEY_1",
    )
    hf_api_key_2: str = Field(
        default="",
        alias="HF_API_KEY_2",
    )
    hf_rotation_cooldown_seconds: float = Field(
        default=60.0,
        alias="HF_ROTATION_COOLDOWN_SECONDS",
    )
    hf_request_timeout_seconds: float = Field(
        default=30.0,
        alias="HF_REQUEST_TIMEOUT_SECONDS",
    )

    # === Database (PostgreSQL + pgvector) ===
    database_url: str = Field(
        default="postgresql+asyncpg://travelmate:travelmate_pass@localhost:5432/travelmate_db",
        alias="DATABASE_URL",
    )

    # === Redis ===
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
    )
    redis_session_ttl: int = Field(
        default=1800,
        alias="REDIS_SESSION_TTL",
    )

    # === Langfuse ===
    langfuse_secret_key: str | None = Field(
        default=None,
        alias="LANGFUSE_SECRET_KEY",
    )
    langfuse_public_key: str | None = Field(
        default=None,
        alias="LANGFUSE_PUBLIC_KEY",
    )
    langfuse_host: str = Field(
        default="http://localhost:3000",
        alias="LANGFUSE_HOST",
    )

    # === App Info & Security ===
    app_env: str = Field(
        default="development",
        alias="APP_ENV",
    )
    app_debug: bool = Field(
        default=True,
        alias="APP_DEBUG",
    )
    bot_version: str = Field(
        default="V1.0",
        alias="BOT_VERSION",
    )
    system_prompt_version: str = Field(
        default="v1",
        alias="SYSTEM_PROMPT_VERSION",
    )
    log_level: str = Field(
        default="DEBUG",
        alias="LOG_LEVEL",
    )
    rate_limit_per_minute: int = Field(
        default=60,
        alias="RATE_LIMIT_PER_MINUTE",
    )
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001,http://localhost:5173",
        alias="CORS_ORIGINS",
    )
    api_secret_key: str = Field(
        default="e4d909c290d0fb1ca068ffaddf22cbd0ffd607f2ef8c1b3f790209c169222cf7",
        alias="API_SECRET_KEY",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a clean string list.

        Returns:
            List of allowed origin URLs.
        """
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def hf_api_keys(self) -> list[str]:
        """Collect non-empty Hugging Face API keys for rotation.

        Returns:
            List of valid Hugging Face API tokens.
        """
        keys = [self.hf_api_key_1, self.hf_api_key_2]
        return [k for k in keys if k]


settings = Settings()
