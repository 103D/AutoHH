from unittest.mock import AsyncMock
from app.providers.ai.base import AIProvider, MatchResult, SkillMatch

class MockAIProvider(AIProvider):
    """Mock AI provider for unit testing matching logic."""
    
    def __init__(self, default_result: MatchResult | None = None):
        self.analyze_job = AsyncMock(return_value=default_result)
        self.adapt_resume = AsyncMock(return_value="Adapted resume text")
        self.generate_cover_letter = AsyncMock(return_value="Generated cover letter text")

    async def analyze_job(self, *args, **kwargs):
        return await self.analyze_job()

    async def adapt_resume(self, *args, **kwargs):
        return await self.adapt_resume()

    async def generate_cover_letter(self, *args, **kwargs):
        return await self.generate_cover_letter()
