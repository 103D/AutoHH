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
    # Optional webhook secret (Telegram sets the
    # X-Telegram-Bot-Api-Secret-Token header; setWebhook secret_token param).
    telegram_webhook_secret: str | None = None
    # Additional chat IDs allowed to talk to the bot (comma-separated).
    # The primary chat is telegram_chat_id; extra chats (e.g. a private chat
    # alongside a group) go here so the inbound flow accepts both.
    telegram_extra_chat_ids: str | None = None

    # Job Fetching
    job_fetch_interval_minutes: int = 30
    job_cleanup_days: int = 90

    # Ingestion resilience: disable a job source after N consecutive failures
    max_consecutive_source_errors: int = 5

    # HeadHunter API User-Agent (required by api.hh.ru; otherwise 403/400).
    # You MUST register an application at https://dev.hh.ru/ to get a valid
    # App ID. Free/public UAs and common email domains are blacklisted.
    # Format: "AppName/Version (contact@yourdomain.com)"
    hh_user_agent: str = "JobHunter/0.1.0 (contact@yourdomain.com)"

    # HeadHunter OAuth (ADR-001): applicant-account integration.
    # Register at https://dev.hh.ru/, redirect URI must match the app settings.
    hh_oauth_client_id: str | None = None
    hh_oauth_client_secret: str | None = None
    hh_oauth_redirect_uri: str | None = None
    # PKCE S256 — enable only for HH apps registered with PKCE support.
    hh_oauth_use_pkce: bool = False
    # OAuth state TTL (connect flow must finish within this window).
    hh_oauth_state_ttl_seconds: int = 600
    # Dedicated Fernet key for encrypting HH tokens at rest.
    # MUST be distinct from SECRET_KEY. Generate:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    hh_credentials_key: str | None = None
    # Background HH sync cadence/limits (ADR-001 milestone 6).
    hh_sync_interval_minutes: int = 15
    hh_sync_batch_size: int = 100
    hh_refresh_lock_ttl_seconds: int = 60

    # Interim ownership boundary (ADR-001 milestone 1): HH endpoints scope
    # everything by this user id until real authentication exists. This is
    # the documented production-rollout gate — do not expose beyond localhost
    # without replacing it with a real auth dependency.
    default_user_id: str = "00000000-0000-0000-0000-000000000001"

    # Scoring Weights — deterministic components (normalized to 1.0 in ScoringEngine)
    score_weight_semantic: float = 0.4  # deprecated: LLM no longer blends into the
                                        # final score; kept for env back-compat only
    score_weight_technical: float = 0.30
    score_weight_experience: float = 0.20
    score_weight_location: float = 0.10
    score_weight_salary: float = 0.10
    score_weight_work_format: float = 0.10
    score_weight_education: float = 0.10
    score_weight_language: float = 0.10

    # Skill importance weights inside the technical component (match model v3).
    # REQUIRED skills are weighted 3x vs OPTIONAL so their absence visibly
    # dominates the technical score.
    score_required_skill_weight: float = 3.0
    score_preferred_skill_weight: float = 1.5
    score_optional_skill_weight: float = 0.5

    # Soft cap for missing REQUIRED skills (match model v3): the final score
    # cannot exceed (100 - N * penalty). A missing mandatory skill is always
    # visible — in the technical component, in the cap and in the breakdown —
    # but is NOT a hard blocker on its own.
    score_missing_required_penalty: float = 25.0

    # Hard requirements (task spec #8): any critical failure => NOT_ELIGIBLE
    hard_filters_enabled: bool = True
    # Business rule: a vacancy may require at most 1.5x the candidate's
    # experience. Documented and configurable (not a hidden heuristic).
    hard_experience_max_factor: float = 1.5
    # Absolute growth buffer so a junior with 0 documented years can still be
    # eligible for entry vacancies ("1+ year") instead of being auto-blocked.
    # Effective allowance = max(years * factor, years + gap).
    hard_experience_max_gap: float = 2.0
    hard_salary_tolerance: float = 0.20

    # LLM cost gate (task spec #29): skip AI analysis when the deterministic
    # score is below this threshold — LLM only for ambiguous/relevant jobs
    llm_gate_enabled: bool = True
    llm_gate_min_deterministic_score: int = 40

    # Feedback loop (task spec #17): match-score bucket boundaries for
    # outcome analytics; "40,55,70,85" -> <40, 40-54, 55-69, 70-84, >=85
    feedback_score_buckets: str = "40,55,70,85"

    # LLM result cache (task spec #28): same vacancy + candidate skills +
    # prompt version => reuse the previous AI analysis instead of paying again
    llm_cache_enabled: bool = True
    llm_cache_ttl_hours: int = 168  # 7 days

    # Prometheus metrics (task spec #22): /metrics endpoint + pipeline counters
    metrics_enabled: bool = True

    # Prompt version stored with analyses and used in cache keys (specs #10/#28)
    prompt_version: str = "v1"

    # Threshold advisor (specs #18/#32): applications per score bucket before
    # suggestions stop being marked as provisional
    threshold_advisor_min_bucket: int = 5

    # === Hermes + GPT-5.5 integration (Phase 4) ===
    # Autonomy mode: READ_ONLY, ASSISTED, or AUTONOMOUS
    hermes_mode: str = "READ_ONLY"
    # GPT-5.5 reasoning provider config
    hermes_gpt_api_key: str | None = None
    hermes_gpt_model: str = "gpt-5.5-turbo"
    hermes_gpt_base_url: str | None = None
    hermes_gpt_max_tokens: int = 2048
    hermes_gpt_temperature: float = 0.3
    # Policy defaults for AUTONOMOUS mode (comma-separated for list values)
    hermes_policy_min_score: int = 50
    hermes_policy_min_salary_max: int | None = None
    hermes_policy_max_salary_max: int | None = None
    hermes_policy_locations: str = ""
    hermes_policy_specializations: str = ""
    hermes_policy_excluded_companies: str = ""
    hermes_policy_employment_types: str = ""
    hermes_policy_work_formats: str = ""
    hermes_policy_max_experience_gap_years: float | None = None
    hermes_policy_allow_top_tier: bool = False
    # Score threshold above which policy-failing jobs get auto-approved with review
    hermes_auto_approve_review_threshold: int = 70

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


    @property
    def telegram_allowed_chat_ids(self) -> set[str]:
        """All chat IDs permitted to interact with the bot (primary + extra)."""
        ids: set[str] = set()
        if self.telegram_chat_id:
            ids.add(str(self.telegram_chat_id))
        for raw in (self.telegram_extra_chat_ids or "").split(","):
            cid = raw.strip()
            if cid:
                ids.add(cid)
        return ids


def get_settings() -> Settings:
    return Settings()


settings = get_settings()
