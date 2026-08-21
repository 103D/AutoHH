"""OpenAI provider implementation."""

import asyncio
import json
import random

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.ai.base import MatchResult

logger = get_logger(__name__)

# Approximate cost per 1K tokens (USD) for common models
MODEL_COSTS = {
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
}


SYSTEM_PROMPT = """You are an expert job matching assistant. Analyze job postings against candidate profiles and provide structured assessments.

IMPORTANT RULES:
1. Be honest about matches and gaps - never invent qualifications
2. Score based on actual fit, not optimism
3. Identify both strengths and concerns
4. Consider practical factors (location, salary, experience level)
5. Provide actionable recommendations

Respond ONLY with valid JSON matching the specified schema."""


class OpenAIProvider:
    """OpenAI API provider for job matching."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        self.api_key = api_key or settings.ai_api_key
        self.model = model or settings.ai_model
        self.max_tokens = max_tokens or settings.ai_max_tokens
        self.temperature = temperature or settings.ai_temperature
        self.base_url = "https://api.openai.com/v1"
        self.timeout = 60.0
        self.max_retries = 3
        self.retry_delay = 1.0

    def _calculate_cost(self, usage: dict) -> tuple[int, float]:
        """Calculate token usage and estimated cost."""
        total_tokens = usage.get("total_tokens", 0)
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        costs = MODEL_COSTS.get(self.model, {"input": 0.001, "output": 0.002})
        cost = (prompt_tokens / 1000 * costs["input"]) + (
            completion_tokens / 1000 * costs["output"]
        )
        return total_tokens, round(cost, 6)

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        payload: dict,
    ) -> dict:
        """Make API request with retry and exponential backoff."""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                last_error = e
                status_code = e.response.status_code
                # Retry on rate limit (429) and server errors (5xx)
                if status_code in (429, 500, 502, 503, 504):
                    delay = self.retry_delay * (2**attempt) + random.uniform(0, 0.5)
                    logger.warning(
                        f"OpenAI API {status_code}, retrying in {delay:.1f}s "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(delay)
                    continue
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                delay = self.retry_delay * (2**attempt) + random.uniform(0, 0.5)
                logger.warning(
                    f"Network error, retrying in {delay:.1f}s "
                    f"(attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                await asyncio.sleep(delay)
                continue

        raise last_error or Exception("Max retries exceeded")

    def _build_analysis_prompt(
        self,
        job_title: str,
        job_company: str,
        job_description: str,
        job_requirements: dict | None,
        candidate_profile: dict,
    ) -> str:
        """Build the analysis prompt."""
        requirements_text = ""
        if job_requirements:
            requirements_text = f"\nJob Requirements:\n{json.dumps(job_requirements, indent=2)}"

        return f"""Analyze this job posting against the candidate profile and provide a match assessment.

JOB POSTING:
Title: {job_title}
Company: {job_company}
Description:
{job_description}
{requirements_text}

CANDIDATE PROFILE:
{json.dumps(candidate_profile, indent=2)}

Provide your analysis as JSON with this exact structure:
{{
  "score": <integer 0-100>,
  "recommendation": "HIGH_PRIORITY" or "APPLY" or "REVIEW" or "IGNORE",
  "matched_skills": [{{"skill": "name", "match_type": "exact|partial|related", "confidence": 0.0-1.0}}],
  "missing_skills": ["skill1", "skill2"],
  "strong_matches": ["match1", "match2"],
  "concerns": ["concern1", "concern2"],
  "reasoning_summary": "Brief explanation",
  "salary_match": true/false/null,
  "location_match": true/false/null,
  "experience_match": true/false/null
}}

Scoring guidelines:
- 90-100: HIGH_PRIORITY - Excellent fit, apply immediately
- 75-89: APPLY - Good fit, should apply
- 60-74: REVIEW - Moderate fit, consider carefully
- 0-59: IGNORE - Poor fit, skip

Be objective and realistic in your assessment."""

    async def analyze_job(
        self,
        job_title: str,
        job_company: str,
        job_description: str,
        job_requirements: dict | None,
        candidate_profile: dict,
    ) -> MatchResult:
        """Analyze job against candidate profile using OpenAI."""
        prompt = self._build_analysis_prompt(
            job_title, job_company, job_description, job_requirements, candidate_profile
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                data = await self._request_with_retry(
                    client,
                    {
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": self.max_tokens,
                        "temperature": self.temperature,
                        "response_format": {"type": "json_object"},
                    },
                )

                content = data["choices"][0]["message"]["content"]
                result_data = json.loads(content)

                # Extract usage and cost
                usage = data.get("usage", {})
                tokens_used, cost_usd = self._calculate_cost(usage)

                # Validate and create MatchResult
                result = MatchResult(**result_data)
                result.tokens_used = tokens_used
                result.cost_usd = cost_usd

                logger.info(
                    f"OpenAI analysis: tokens={tokens_used}, cost=${cost_usd:.6f}"
                )
                return result

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response: {e}")
            raise
        except Exception as e:
            logger.error(f"OpenAI provider error: {e}")
            raise

    async def adapt_resume(
        self,
        resume_text: str,
        job_title: str,
        job_description: str,
        key_requirements: list[str],
    ) -> str:
        """Adapt resume for specific job using OpenAI."""
        prompt = f"""Adapt this resume to better match the target job.

RESUME:
{resume_text}

TARGET JOB:
Title: {job_title}
Description:
{job_description}

KEY REQUIREMENTS TO HIGHLIGHT:
{json.dumps(key_requirements, indent=2)}

RULES:
1. Keep ALL factual information accurate
2. Do NOT invent experience, skills, or achievements
3. Reorganize bullet points to highlight relevant experience
4. Adjust summary/objective to align with the role
5. Use keywords from the job description naturally
6. Maintain professional tone

Return ONLY the adapted resume text, no explanations."""

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                data = await self._request_with_retry(
                    client,
                    {
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an expert resume writer. Adapt resumes while maintaining factual accuracy.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 2000,
                        "temperature": 0.3,
                    },
                )

                return data["choices"][0]["message"]["content"].strip()

        except Exception as e:
            logger.error(f"Resume adaptation error: {e}")
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
        """Generate cover letter using OpenAI."""
        style_guides = {
            "professional": "Formal business tone, structured paragraphs",
            "casual": "Friendly but professional, conversational",
            "enthusiastic": "Energetic and passionate while remaining professional",
        }

        prompt = f"""Write a cover letter for a job application.

CANDIDATE: {candidate_name}
POSITION: {job_title}
COMPANY: {company_name}

KEY MATCHING POINTS:
{json.dumps(key_matches, indent=2)}

JOB DESCRIPTION:
{job_description[:1000]}...

STYLE: {style_guides.get(style, style_guides['professional'])}

RULES:
1. Be specific about qualifications mentioned in key matches
2. Do NOT invent experience or skills
3. Keep it concise (250-350 words)
4. Show genuine interest in the role and company
5. Include a clear call to action

Return ONLY the cover letter text."""

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                data = await self._request_with_retry(
                    client,
                    {
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an expert cover letter writer. Create compelling, honest application letters.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 1000,
                        "temperature": 0.5,
                    },
                )

                return data["choices"][0]["message"]["content"].strip()

        except Exception as e:
            logger.error(f"Cover letter generation error: {e}")
            raise
