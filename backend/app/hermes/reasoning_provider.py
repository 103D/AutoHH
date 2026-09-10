"""GPT-5.5 reasoning-only provider for Hermes.

GPT-5.5 thinks — it analyzes semantic fit, identifies risks, extracts
requirements and equivalences, and proposes recommendations. It does NOT
assign the final numeric score: that is always computed by the deterministic
ScoringEngine inside AutoHH.

The provider exposes two methods:
- ``analyze_job_semantics``: returns semantic analysis (no score).
- ``reason_about_application``: returns reasoning + decision context.
"""

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AIProviderError
from app.core.logging import get_logger
from app.providers.ai.base import MatchResult

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lightweight data types used by the orchestrator for reasoning steps.
# ---------------------------------------------------------------------------

@dataclass
class ReasoningRequest:
    """A single reasoning request passed to GPT-5.5."""

    goal: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningResponse:
    """Result of a GPT-5.5 reasoning step."""

    reasoning: str = ""
    proposed_actions: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""


DEFAULT_MODEL = "gpt-5.5-turbo"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 2048


def _truncate_profile(profile: dict, max_len: int = 2000) -> dict:
    """Reduce profile payload size for prompt injection."""
    result = {}
    for k, v in profile.items():
        if len(result) * 100 > max_len:
            break
        result[k] = v
    return result


class GPT55ReasoningProvider:
    """Reasoning-only provider wrapping the OpenAI-compatible GPT-5.5 API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key or settings.hermes_gpt_api_key or settings.ai_api_key
        self.model = model or settings.hermes_gpt_model or DEFAULT_MODEL
        self.max_tokens = max_tokens or settings.hermes_gpt_max_tokens or DEFAULT_MAX_TOKENS
        self.temperature = temperature or settings.hermes_gpt_temperature or DEFAULT_TEMPERATURE
        self.base_url = base_url or settings.hermes_gpt_base_url or "https://api.openai.com/v1"
        self.timeout = 60.0

    @property
    def name(self) -> str:
        return "gpt-5.5-reasoning"

    async def analyze_job_semantics(
        self,
        job_title: str,
        job_company: str,
        job_description: str,
        job_requirements: dict | None,
        candidate_profile: dict,
    ) -> MatchResult:
        """Analyze job semantics against a candidate profile.

        Returns a MatchResult with semantic fields populated. The ``score`` and
        ``recommendation`` fields are advisory — the deterministic engine
        overrides them.
        """
        prompt = self._build_reasoning_prompt(
            job_title, job_company, job_description, job_requirements, candidate_profile
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                data = await self._request_with_retry(
                    client,
                    {
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": self._system_prompt()},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": self.max_tokens,
                        "temperature": self.temperature,
                        "response_format": {"type": "json_object"},
                    },
                )

                content = data["choices"][0]["message"]["content"]
                result_data = json.loads(content)

                usage = data.get("usage", {})
                tokens_used, cost_usd = self._calculate_cost(usage)

                result = MatchResult(**result_data)
                result.tokens_used = tokens_used
                result.cost_usd = cost_usd

                logger.info(
                    "GPT-5.5 reasoning for '%s' @ %s: tokens=%s cost=$%.6f",
                    job_title, job_company, tokens_used, cost_usd,
                )
                return result

        except httpx.HTTPStatusError as e:
            logger.error("GPT-5.5 API error: %s %s", e.response.status_code, e.response.text)
            raise AIProviderError(f"GPT-5.5 API error: {e.response.status_code}") from e
        except json.JSONDecodeError as e:
            logger.error("Failed to parse GPT-5.5 response: %s", e)
            raise AIProviderError("GPT-5.5 returned malformed JSON") from e
        except Exception as e:
            logger.error("GPT-5.5 reasoning provider error: %s", e)
            raise AIProviderError(f"GPT-5.5 reasoning error: {e}") from e

    async def reason_about_application(
        self,
        job_title: str,
        job_company: str,
        job_description: str,
        match_score: int,
        recommendation: str,
        candidate_profile: dict,
        concerns: list[str] | None = None,
        missing_skills: list[str] | None = None,
    ) -> dict:
        """Ask GPT-5.5 whether the candidate should apply, given a match result.

        Returns a reasoning dict (not a score). The final decision remains
        Hermes' responsibility (mode + policy + gate).
        """
        prompt = (
            f"You are advising a job applicant. Given the context, provide a "
            f"structured JSON recommendation on whether to apply.\n\n"
            f"Job: {job_title} at {job_company}\n"
            f"Description: {job_description[:1500]}\n"
            f"Deterministic match score: {match_score}/100\n"
            f"Recommendation: {recommendation}\n"
            f"Candidate profile: {json.dumps(_truncate_profile(candidate_profile))}\n"
            f"Concerns: {json.dumps(concerns or [])}\n"
            f"Missing skills: {json.dumps(missing_skills or [])}\n\n"
            f"Respond with JSON: {{\"should_apply\": bool, \"confidence\": 0-100, "
            f"\"reasoning\": str, \"key_risks\": [str], \"key_strengths\": [str]}}"
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                data = await self._request_with_retry(
                    client,
                    {
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "You are a career advisor."},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": self.max_tokens,
                        "temperature": self.temperature,
                        "response_format": {"type": "json_object"},
                    },
                )
                content = data["choices"][0]["message"]["content"]
                result = json.loads(content)
                usage = data.get("usage", {})
                tokens, cost = self._calculate_cost(usage)
                result["tokens_used"] = tokens
                result["cost_usd"] = cost
                return result
        except (httpx.HTTPStatusError, json.JSONDecodeError, Exception) as e:
            logger.error("GPT-5.5 application reasoning failed: %s", e)
            raise AIProviderError(f"GPT-5.5 application reasoning error: {e}") from e

    def _system_prompt(self) -> str:
        return (
            "You are Hermes GPT-5.5 reasoning model. Analyze semantics, identify "
            "risks, and extract structured information. You NEVER assign the final "
            "numeric score — the deterministic engine handles that. Respond ONLY with "
            "valid JSON."
        )

    def _build_reasoning_prompt(
        self,
        job_title: str,
        job_company: str,
        job_description: str,
        job_requirements: dict | None,
        candidate_profile: dict,
    ) -> str:
        reqs = json.dumps(job_requirements or {})
        prof = json.dumps(_truncate_profile(candidate_profile))
        return f"""Analyze this vacancy for the candidate.

Job Title: {job_title}
Company: {job_company}
Job Requirements: {reqs}
Job Description:
{job_description[:3000]}

Candidate Profile:
{prof}

Rules:
1. List all technical requirements with importance (REQUIRED/PREFERRED/OPTIONAL).
2. Identify skill_equivalences: candidate skills that prove competence for a required skill.
3. Identify strong_matches and concerns (be honest about gaps).
4. Provide a brief reasoning_summary.
5. Do NOT assign a numeric score — deterministic engine handles that.
6. seniority_signal: infer junior/middle/senior/lead.
7. domain_signal: infer retail/product/bi/general.

Respond with JSON:
{{"score": 50, "recommendation": "SOLID_MATCH",
"matched_skills": [{"skill": "...", "match_type": "exact", "confidence": 0.9}],
"missing_skills": ["..."], "strong_matches": ["..."], "concerns": ["..."],
"reasoning_summary": "...",
"requirements": [{"skill": "...", "importance": "REQUIRED", "note": null}],
"skill_equivalences": [{"job_skill": "...", "candidate_skill": "...", "note": null}],
"seniority_signal": "middle", "domain_signal": "general"}}"""

    def _calculate_cost(self, usage: dict) -> tuple[int | None, float | None]:
        tokens = usage.get("total_tokens")
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        input_cost = input_tokens * 0.0015 / 1000
        output_cost = output_tokens * 0.006 / 1000
        cost = input_cost + output_cost
        return tokens, round(cost, 6)

    async def _request_with_retry(self, client: httpx.AsyncClient, payload: dict, max_retries: int = 3) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        for attempt in range(max_retries):
            try:
                resp = await client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=headers
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < max_retries - 1:
                    logger.warning("GPT-5.5 retry %d/%d after status %s",
                                   attempt + 1, max_retries, e.response.status_code)
                    continue
                raise
            except Exception:
                if attempt < max_retries - 1:
                    continue
                raise
        raise AIProviderError("GPT-5.5 request exhausted retries")


# Backward-compatible alias
ReasoningProvider = GPT55ReasoningProvider
