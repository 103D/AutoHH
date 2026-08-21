"""AI Provider factory with fallback support."""

from typing import Any

from app.core.config import settings
from app.core.exceptions import AIProviderError
from app.core.logging import get_logger
from app.providers.ai.base import AIProvider, MatchResult
from app.providers.ai.openai_provider import OpenAIProvider

logger = get_logger(__name__)


class FallbackAIProvider:
    """AI provider wrapper that tries primary, then fallback provider."""

    def __init__(self, primary: AIProvider, fallback: AIProvider | None = None):
        self.primary = primary
        self.fallback = fallback

    async def analyze_job(
        self,
        job_title: str,
        job_company: str,
        job_description: str,
        job_requirements: dict | None,
        candidate_profile: dict,
    ) -> MatchResult:
        """Try primary provider, fallback on failure."""
        try:
            return await self.primary.analyze_job(
                job_title, job_company, job_description, job_requirements, candidate_profile
            )
        except Exception as e:
            if self.fallback:
                logger.warning(f"Primary AI provider failed, using fallback: {e}")
                return await self.fallback.analyze_job(
                    job_title, job_company, job_description, job_requirements, candidate_profile
                )
            raise

    async def adapt_resume(
        self,
        resume_text: str,
        job_title: str,
        job_description: str,
        key_requirements: list[str],
    ) -> str:
        """Try primary provider, fallback on failure."""
        try:
            return await self.primary.adapt_resume(
                resume_text, job_title, job_description, key_requirements
            )
        except Exception as e:
            if self.fallback:
                logger.warning(f"Primary AI provider failed, using fallback: {e}")
                return await self.fallback.adapt_resume(
                    resume_text, job_title, job_description, key_requirements
                )
            raise

    async def generate_cover_letter(
        self,
        candidate_name: str,
        job_title: str,
        company_name: str,
        job_description: str,
        key_matches: list[str],
        style: str = "professional",
    ) -> str:
        """Try primary provider, fallback on failure."""
        try:
            return await self.primary.generate_cover_letter(
                candidate_name, job_title, company_name, job_description, key_matches, style
            )
        except Exception as e:
            if self.fallback:
                logger.warning(f"Primary AI provider failed, using fallback: {e}")
                return await self.fallback.generate_cover_letter(
                    candidate_name, job_title, company_name, job_description, key_matches, style
                )
            raise


def create_ai_provider(
    provider_type: str | None = None,
    config: dict[str, Any] | None = None,
) -> AIProvider:
    """
    Create AI provider instance based on configuration.

    If OpenRouter API key is configured alongside OpenAI, creates a
    FallbackAIProvider that tries primary, then fallback on failure.

    Args:
        provider_type: Provider type (openai, openrouter). Defaults to settings.ai_provider
        config: Optional configuration override

    Returns:
        AIProvider instance

    Raises:
        AIProviderError: If provider type is not supported
    """
    provider_type = provider_type or settings.ai_provider
    config = config or {}

    providers = {
        "openai": OpenAIProvider,
        "openrouter": OpenAIProvider,
    }

    provider_class = providers.get(provider_type)
    if not provider_class:
        raise AIProviderError(
            f"Unsupported AI provider: {provider_type}. "
            f"Supported: {list(providers.keys())}"
        )

    # Build primary provider
    if provider_type == "openrouter":
        primary = provider_class(
            api_key=config.get("api_key") or settings.openrouter_api_key or settings.ai_api_key,
            model=config.get("model") or settings.openrouter_model,
            max_tokens=config.get("max_tokens") or settings.ai_max_tokens,
            temperature=config.get("temperature") or settings.ai_temperature,
        )
    else:
        primary = provider_class(
            api_key=config.get("api_key") or settings.ai_api_key,
            model=config.get("model") or settings.ai_model,
            max_tokens=config.get("max_tokens") or settings.ai_max_tokens,
            temperature=config.get("temperature") or settings.ai_temperature,
        )

    # Build fallback provider if alternative is configured
    fallback = None
    if provider_type == "openai" and settings.openrouter_api_key:
        logger.info("Configuring OpenRouter as fallback AI provider")
        fallback = OpenAIProvider(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
        )
    elif provider_type == "openrouter" and settings.ai_api_key != "placeholder":
        logger.info("Configuring OpenAI as fallback AI provider")
        fallback = OpenAIProvider(
            api_key=settings.ai_api_key,
            model=settings.ai_model,
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
        )

    if fallback:
        return FallbackAIProvider(primary, fallback)

    return primary
