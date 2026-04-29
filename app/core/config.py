"""Configuration module for the WhisperX FastAPI application."""

from functools import lru_cache
from typing import Optional

import torch
from pydantic import Field, SecretStr, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas import ComputeType, Device, WhisperModel


class DatabaseSettings(BaseSettings):
    """Database configuration settings."""

    DB_URL: str = Field(
        default="sqlite:///records.db",
        description="Database connection URL",
    )
    DB_ECHO: bool = Field(
        default=False,
        description="Echo SQL queries for debugging",
    )


class WhisperSettings(BaseSettings):
    """WhisperX ML model configuration settings."""

    HF_TOKEN: Optional[str] = Field(
        default=None,
        description="HuggingFace API token for model downloads",
    )
    WHISPER_MODEL: WhisperModel = Field(
        default=WhisperModel.tiny,
        description="Whisper model size to use",
    )
    DEFAULT_LANG: str = Field(
        default="en",
        description="Default language for transcription",
    )
    LANGUAGE_MODEL_OVERRIDES: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Language-specific model overrides. Maps ISO 639-1 language codes "
            "to local CTranslate2 model paths or HuggingFace repo IDs. "
            "Example: {'lv': '/path/to/ct2-int8'}"
        ),
    )
    DEVICE: Device = Field(
        default_factory=lambda: Device.cuda
        if torch.cuda.is_available()
        else Device.cpu,
        description="Device to use for computation (cuda or cpu)",
    )
    COMPUTE_TYPE: ComputeType = Field(
        default_factory=lambda: (
            ComputeType.float16 if torch.cuda.is_available() else ComputeType.int8
        ),
        description="Compute type for model inference",
    )

    AUDIO_EXTENSIONS: set[str] = {
        ".mp3",
        ".wav",
        ".awb",
        ".aac",
        ".ogg",
        ".oga",
        ".m4a",
        ".wma",
        ".amr",
    }
    VIDEO_EXTENSIONS: set[str] = {".mp4", ".mov", ".avi", ".wmv", ".mkv"}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ALLOWED_EXTENSIONS(self) -> set[str]:
        """Compute allowed extensions by combining audio and video."""
        return self.AUDIO_EXTENSIONS | self.VIDEO_EXTENSIONS

    def resolve_model_for_language(self, model: str, language: str) -> tuple[str, str]:
        """
        Resolve the model and compute type for a given language.

        If a language-specific override is configured, returns the override
        path and preserves the default compute type (typically float16).
        Otherwise returns the original model and compute type unchanged.

        Returns:
            Tuple of (model_name_or_path, compute_type)
        """
        override = self.LANGUAGE_MODEL_OVERRIDES.get(language)
        if override:
            return override, self.COMPUTE_TYPE.value
        return model, self.COMPUTE_TYPE.value

    @model_validator(mode="after")
    def validate_compute_type_for_cpu(self) -> "WhisperSettings":
        """Validate that CPU device uses int8 compute type."""
        if self.DEVICE == Device.cpu and self.COMPUTE_TYPE != ComputeType.int8:
            # Auto-correct instead of raising error
            self.COMPUTE_TYPE = ComputeType.int8
        return self


class LoggingSettings(BaseSettings):
    """Logging configuration settings."""

    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    LOG_FORMAT: str = Field(
        default="text",
        description="Log format: text or json",
    )
    FILTER_WARNING: bool = Field(
        default=True,
        description="Filter specific warnings",
    )


class CallbackSettings(BaseSettings):
    """Callback configuration settings."""

    CALLBACK_TIMEOUT: int = Field(
        default=10,
        description="Timeout for callback requests in seconds",
    )
    CALLBACK_MAX_RETRIES: int = Field(
        default=3,
        description="Maximum number of retries for failed callback requests",
    )


class AuthSettings(BaseSettings):
    """Authentication configuration settings.

    Per .planning/phases/11-auth-core-modules-services-di/11-CONTEXT.md §138-147 (locked):
    - JWT HS256 secret (required; fail loudly if missing in non-test envs).
    - Argon2id OWASP params: m=19456 KiB, t=2, p=1.
    - CSRF double-submit secret (required for prod; defaultable in test envs).
    """

    model_config = SettingsConfigDict(
        env_prefix="AUTH__",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    JWT_SECRET: SecretStr = Field(
        default=SecretStr("change-me-dev-only"),
        description="HS256 secret for session tokens (override in production)",
    )
    JWT_TTL_DAYS: int = Field(default=7, description="JWT validity period (days)")
    ARGON2_M_COST: int = Field(default=19456, description="Argon2 memory cost (KiB)")
    ARGON2_T_COST: int = Field(default=2, description="Argon2 time cost (iterations)")
    ARGON2_PARALLELISM: int = Field(default=1, description="Argon2 parallelism")
    CSRF_SECRET: SecretStr = Field(
        default=SecretStr("change-me-dev-only"),
        description="CSRF double-submit token signing secret",
    )

    # ----- Phase 13 atomic-cutover envs -----
    V2_ENABLED: bool = Field(
        default=False,
        description="Phase 13 feature flag: false=legacy BearerAuthMiddleware, true=DualAuthMiddleware",
    )
    FRONTEND_URL: str = Field(
        default="http://localhost:5173",
        description="Single-origin allowlist for CORSMiddleware (ANTI-06)",
    )
    COOKIE_SECURE: bool = Field(
        default=False,
        description="Set Secure cookie attr (production must be true)",
    )
    COOKIE_DOMAIN: str = Field(
        default="",
        description="Cookie Domain attribute; empty = browser default (request host)",
    )
    TRUST_CF_HEADER: bool = Field(
        default=False,
        description="Trust CF-Connecting-IP for slowapi key_func (RATE-01)",
    )
    HCAPTCHA_ENABLED: bool = Field(
        default=False,
        description="Enable hCaptcha verify on register/login (ANTI-05; default off)",
    )
    HCAPTCHA_SITE_KEY: str = Field(
        default="",
        description="hCaptcha public site key (ANTI-05)",
    )
    HCAPTCHA_SECRET: SecretStr = Field(
        default=SecretStr(""),
        description="hCaptcha verify endpoint secret (ANTI-05)",
    )

    @model_validator(mode="after")
    def _reject_dev_defaults_in_production(self) -> "AuthSettings":
        """Production safety: refuse to boot with the dev-only secret defaults.

        pydantic-settings cannot conditionally require fields, so we use harmless
        dev defaults and assert at construction time that production never sees them.
        """
        import os

        if os.environ.get("ENVIRONMENT", "").lower() != "production":
            return self
        dev_default = "change-me-dev-only"
        if self.JWT_SECRET.get_secret_value() == dev_default:
            raise ValueError("AUTH__JWT_SECRET must be set in production")
        if self.CSRF_SECRET.get_secret_value() == dev_default:
            raise ValueError("AUTH__CSRF_SECRET must be set in production")
        # Phase 13: V2 cutover requires real secrets in production
        if self.V2_ENABLED and self.FRONTEND_URL == "http://localhost:5173":
            raise ValueError(
                "AUTH__FRONTEND_URL must be set when AUTH__V2_ENABLED=true in production"
            )
        if self.V2_ENABLED and not self.COOKIE_SECURE:
            raise ValueError(
                "AUTH__COOKIE_SECURE must be true when AUTH__V2_ENABLED=true in production"
            )
        return self


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_nested_delimiter="__",
    )

    ENVIRONMENT: str = Field(
        default="production",
        description="Environment: development, testing, production",
    )
    DEV: bool = Field(
        default=False,
        description="Development mode flag",
    )

    # Nested settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    whisper: WhisperSettings = Field(default_factory=WhisperSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    callback: CallbackSettings = Field(default_factory=CallbackSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def normalize_environment(cls, v: str) -> str:
        """Normalize environment to lowercase."""
        return str(v).lower() if v else "production"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance (singleton pattern).

    Returns:
        Settings: The application settings instance.
    """
    return Settings()


# Legacy Config class for backward compatibility during migration
# This will be removed once all references are updated
class Config:
    """DEPRECATED: Legacy configuration class. Use get_settings() instead."""

    _settings = get_settings()

    # Delegate to new settings
    LANG = _settings.whisper.DEFAULT_LANG
    HF_TOKEN = _settings.whisper.HF_TOKEN
    WHISPER_MODEL = _settings.whisper.WHISPER_MODEL
    DEVICE = _settings.whisper.DEVICE
    COMPUTE_TYPE = _settings.whisper.COMPUTE_TYPE
    ENVIRONMENT = _settings.ENVIRONMENT
    LOG_LEVEL = _settings.logging.LOG_LEVEL
    AUDIO_EXTENSIONS = _settings.whisper.AUDIO_EXTENSIONS
    VIDEO_EXTENSIONS = _settings.whisper.VIDEO_EXTENSIONS
    ALLOWED_EXTENSIONS = _settings.whisper.ALLOWED_EXTENSIONS
    DB_URL = _settings.database.DB_URL
