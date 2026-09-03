from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: PostgresDsn | None = None

    # Redis
    redis_url: RedisDsn | None = None

    # AI Provider
    ai_provider: str = "openai"
    ai_api_key: str = "placeholder"
    ai_model: str = "gpt-4o-mini"
    ai_max_tokens: int = 2000
    ai_temperature: float = 0.3
    # Optional: override the API base URL (e.g. http://omniroute:20128/v1).
    # When unset, OpenAIProvider uses https://api.openai.com/v1.
    ai_base_url: str | None = None

    # OpenRouter (optional) — use a real model name
    openrouter_api_key: str | None = None
    openrouter_model: str = "anthropic/claude-3.5-sonnet"

    # Telegram
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # Job Fetching
    job_fetch_interval_minutes: int = 30
    job_cleanup_days: int = 90

    # HeadHunter API User-Agent (required by api.hh.ru; otherwise 403).
    # Format: "AppName/Version (contact@example.com)"
    hh_user_agent: str = "JobHunter/0.1.0 (https://github.com/103D/AutoHH)"

    # Scoring Weights
    score_weight_semantic: float = 0.4
    score_weight_technical: float = 0.3
    score_weight_experience: float = 0.2
    score_weight_other: float = 0.1

    # Match category thresholds (matching v2)
    threshold_dream_job: int = 85
    threshold_stretch: int = 70
    threshold_solid_match: int = 55
    threshold_market_research: int = 40
    threshold_learning: int = 25

    # Stretch classification
    stretch_experience_min_factor: float = 0.8
    stretch_experience_max_factor: float = 1.5
    stretch_max_missing_skills: int = 3
    stretch_salary_max_increase: float = 0.40

    # API
    api_v1_prefix: str = "/api/v1"
    secret_key: str = Field(default="change-me-in-production")
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    # Logging
    log_level: str = "INFO"

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if v == "change-me-in-production":
            import warnings

            warnings.warn(
                "Using default secret key. Set SECRET_KEY environment variable in production!",
                UserWarning,
                stacklevel=2,
            )
        return v


def get_settings() -> Settings:
    return Settings()


settings = get_settings()
