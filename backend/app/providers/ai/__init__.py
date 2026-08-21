"""AI Provider module for job matching and analysis."""

from app.providers.ai.base import AIProvider
from app.providers.ai.factory import create_ai_provider

__all__ = ["AIProvider", "create_ai_provider"]
