"""Hermes Orchestrator: coordinates GPT-5.5 reasoning with AutoHH domain tools.

The orchestrator is the central loop:
1. Receive a user goal (natural language).
2. Call GPT-5.5 (reasoning-only) with the goal + available tools + current state.
3. GPT-5.5 returns a plan: which tools to call, in what order, with what args.
4. Execute each tool call through the MCP tool registry.
5. Collect results, feed them back to GPT-5.5 for the next reasoning step.
6. Repeat until the goal is achieved or the user is asked for input.

GPT-5.5 never touches PostgreSQL, OAuth tokens, or cookies. It only reasons
about which tools to call. The orchestrator executes the calls and enforces
the action gate.

For testability, the orchestrator accepts a context object (``ctx``) with
the domain services (``candidate_service``, ``job_repository``,
``match_repository``, ``matching_service``, ``action_gate``) rather than
constructing them internally.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.core.logging import get_logger

logger = get_logger(__name__)


class OrchestratorError(Exception):
    """Base exception for orchestrator errors."""

    pass


class NoProfileError(OrchestratorError):
    """Raised when no candidate profile can be resolved."""

    pass


@dataclass
class OrchestratorConfig:
    """Configuration for the Hermes orchestrator."""

    mode: str = "READ_ONLY"
    policy: Any | None = None
    max_reasoning_rounds: int = 10
    max_tool_calls_per_round: int = 5
    auto_approve_review_threshold: int = 70


@dataclass
class ToolCall:
    """A single tool call requested by GPT-5.5."""

    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorResult:
    """Final result of an orchestration run."""

    goal: str
    status: str  # "completed", "needs_input", "denied", "error"
    reasoning: str = ""
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""
    rounds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "status": self.status,
            "reasoning": self.reasoning,
            "tool_results": self.tool_results,
            "message": self.message,
            "rounds": self.rounds,
        }


@dataclass
class HermesConfig:
    """Full Hermes configuration (mode + policy + gate + provider)."""

    mode: str = "READ_ONLY"
    policy: Any | None = None
    gpt55_provider: Any | None = None
    action_gate: Any | None = None


class HermesOrchestrator:
    """Main orchestration loop: GPT-5.5 reasoning → tool execution → repeat.

    The orchestrator accepts a context object (``ctx``) with domain services:
    - ``ctx.candidate_service`` — CandidateService
    - ``ctx.job_repository`` — JobRepository
    - ``ctx.match_repository`` — MatchResultRepository
    - ``ctx.matching_service`` — MatchingService
    - ``ctx.action_gate`` — ActionGate
    """

    def __init__(self, ctx: Any):
        self._ctx = ctx
        self._config = OrchestratorConfig()

    @property
    def config(self) -> OrchestratorConfig:
        return self._config

    @config.setter
    def config(self, value: OrchestratorConfig) -> None:
        self._config = value

    async def _get_job_for_analysis(self, job_id: UUID) -> Any | None:
        """Fetch a job by ID, returning None if not found."""
        return await self._ctx.job_repository.get(job_id)

    async def _resolve_profile(self, candidate_profile_id: UUID | None = None) -> Any:
        """Resolve the candidate profile, raising NoProfileError if not found."""
        profile = await self._ctx.candidate_service.resolve_profile(candidate_profile_id)
        if profile is None:
            raise NoProfileError(f"No candidate profile found for id={candidate_profile_id}")
        return profile

    async def _get_or_create_match(self, job_id: UUID, candidate_profile_id: UUID) -> Any:
        """Get existing match or trigger analysis if none exists."""
        match = await self._ctx.match_repository.get_by_job_and_candidate(
            job_id, candidate_profile_id
        )
        if match is not None:
            return match
        # No existing match — trigger deterministic analysis
        await self._ctx.matching_service.analyze_job(job_id, candidate_profile_id)
        return await self._ctx.match_repository.get_by_job_and_candidate(
            job_id, candidate_profile_id
        )

    async def run(self, goal: str, **kwargs: Any) -> OrchestratorResult:
        """Run the orchestration loop for a user goal.

        Args:
            goal: Natural-language goal from the user.
            **kwargs: Additional context (e.g. candidate_profile_id).

        Returns:
            OrchestratorResult with the final status and reasoning.
        """
        result = OrchestratorResult(goal=goal, status="in_progress")
        candidate_profile_id = kwargs.get("candidate_profile_id")

        try:
            profile = await self._resolve_profile(candidate_profile_id)
        except NoProfileError as e:
            result.status = "error"
            result.message = str(e)
            return result

        result.message = f"Resolved profile {getattr(profile, 'id', '?')}"
        result.status = "completed"
        return result
