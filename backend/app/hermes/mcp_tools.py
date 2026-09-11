"""Hermes MCP Tool surface.

Exposes AutoHH domain operations as tools that GPT-5.5 can call through
Hermes. Every tool call passes through the ActionGate first: read tools
are always allowed; mutating tools are gated by AutonomyMode + UserPolicy.

Hermes never writes to PostgreSQL directly — it delegates to domain services
and only carries the ActionDecision in the response so the caller (or an
outer layer) can perform the actual write.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.core.logging import get_logger
from app.hermes.approval_gate import (
    ActionContext,
    ActionType,
    ApprovalStatus,
)

logger = get_logger(__name__)


class McpToolError(Exception):
    """Raised when a tool call is denied or fails."""

    pass


@dataclass
class ToolResult:
    """Result of a single MCP tool call."""

    tool: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolContext:
    """Execution context carried through a tool call pipeline."""

    job_id: UUID | None = None
    candidate_profile_id: UUID | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class HermesMcpTools:
    """MCP tool registry with gate enforcement.

    Takes a context object (``ctx``) with domain services and an ActionGate,
    and exposes async tool methods that GPT-5.5 can invoke.
    """

    def __init__(self, ctx: Any):
        self._ctx = ctx
        self._gate = ctx.action_gate

    def _require_write_access(self) -> None:
        """Raise if the current mode does not permit mutations."""
        if not self._gate.can_mutate():
            raise McpToolError(f"Mode {self._gate.mode} does not permit mutating operations")

    def _build_context(
        self,
        action_name: str,
        job: Any | None = None,
        match: Any | None = None,
        profile: Any | None = None,
    ) -> ActionContext:
        """Build an ActionContext from the given entities."""
        action = ActionType(action_name)
        return ActionContext(
            action=action,
            job=job,
            match=match,
            profile=profile,
            match_score=getattr(match, "score", None) if match else None,
        )

    def _build_update_context(self, action_name: str, application: Any) -> ActionContext:
        """Build an ActionContext for update-style actions."""
        action = ActionType(action_name)
        job_id = getattr(application, "job_id", None)
        profile_id = getattr(application, "candidate_profile_id", None)
        return ActionContext(
            action=action,
            job_id=job_id,
            candidate_profile_id=profile_id,
            application_id=getattr(application, "id", None),
        )

    async def search_jobs(self, query: str, limit: int = 10) -> ToolResult:
        """Search jobs by query string (read-only)."""
        self._gate.can_read()
        jobs = await self._ctx.job_repository.get_multi(0, limit)
        return ToolResult(
            tool="search_jobs",
            data={"jobs": [str(getattr(j, "id", "?")) for j in jobs]},
        )

    async def get_job_detail(self, job_id: UUID) -> ToolResult:
        """Get full job details (read-only)."""
        self._gate.can_read()
        job = await self._ctx.job_repository.get(job_id)
        return ToolResult(
            tool="get_job_detail",
            data={"job_id": str(job_id), "found": job is not None},
        )

    async def analyze_job(
        self, job_id: UUID, candidate_profile_id: UUID | None = None
    ) -> ToolResult:
        """Analyze a job against the candidate profile (read-only scoring)."""
        self._gate.can_read()
        result = await self._ctx.matching_service.analyze_job(job_id, candidate_profile_id)
        return ToolResult(
            tool="analyze_job",
            data={
                "score": getattr(result, "score", 0),
                "recommendation": getattr(result, "recommendation", "UNKNOWN"),
            },
        )

    async def get_match_result(self, job_id: UUID, candidate_profile_id: UUID) -> ToolResult:
        """Get the match result for a job + profile pair (read-only)."""
        self._gate.can_read()
        match = await self._ctx.match_repository.get_by_job_and_candidate(
            job_id, candidate_profile_id
        )
        return ToolResult(
            tool="get_match_result",
            data={
                "found": match is not None,
                "score": getattr(match, "score", 0) if match else 0,
            },
        )

    async def get_gap_analysis(
        self, job_id: UUID, candidate_profile_id: UUID | None = None
    ) -> ToolResult:
        """Get a detailed skill-gap analysis for a job (read-only)."""
        self._gate.can_read()
        result = await self._ctx.matching_service.get_gap_analysis(job_id, candidate_profile_id)
        if hasattr(result, "model_dump"):
            data = result.model_dump(mode="json")
        else:
            data = dict(result) if result else {}
        return ToolResult(tool="get_gap_analysis", data=data)

    async def recommend_resume(
        self, job_id: UUID, candidate_profile_id: UUID | None = None
    ) -> ToolResult:
        """Recommend the best resume profile for a vacancy (read-only)."""
        self._gate.can_read()
        result = await self._ctx.matching_service.recommend_resume(job_id, candidate_profile_id)
        if hasattr(result, "model_dump"):
            data = result.model_dump(mode="json")
        else:
            data = dict(result) if result else {}
        return ToolResult(tool="recommend_resume", data=data)

    # --- Mutating tools (gate-checked) ---

    async def override_recommendation(
        self,
        job_id: UUID,
        category: str,
        candidate_profile_id: UUID | None = None,
    ) -> ToolResult:
        """Manually override the match category for a job."""
        self._require_write_access()
        decision = self._gate.evaluate(self._build_context("override_recommendation"))
        if decision.status == ApprovalStatus.DENIED:
            raise McpToolError(f"Action denied: {decision.reason}")
        await self._ctx.matching_service.set_recommendation_override(
            job_id, category, candidate_profile_id
        )
        return ToolResult(
            tool="override_recommendation",
            data={
                "job_id": str(job_id),
                "category": category,
                "approval": decision.to_dict(),
            },
        )

    async def create_application(
        self,
        job_id: UUID,
        resume_profile_id: UUID,
        candidate_profile_id: UUID | None = None,
    ) -> ToolResult:
        """Create a job application (mutating, gate-checked)."""
        self._require_write_access()
        profile = await self._ctx.candidate_service.resolve_profile(candidate_profile_id)
        job = await self._ctx.job_repository.get(job_id)
        if not job:
            raise McpToolError(f"Job {job_id} not found")
        match = await self._ctx.match_repository.get_by_job_and_candidate(job_id, profile.id)
        if not match:
            await self._ctx.matching_service.analyze_job(job_id, profile.id)
            match = await self._ctx.match_repository.get_by_job_and_candidate(job_id, profile.id)
        decision = self._gate.evaluate(
            self._build_context("create_application", job, match, profile)
        )
        if decision.status == ApprovalStatus.DENIED:
            raise McpToolError(f"Action denied: {decision.reason}")

        # Delegate creation to the application service on the context
        application = await self._ctx.application_service.create(
            job_id=job_id,
            candidate_profile_id=profile.id,
            resume_profile_id=resume_profile_id,
        )
        return ToolResult(
            tool="create_application",
            data={
                "application_id": str(getattr(application, "id", "?")),
                "approval": decision.to_dict(),
            },
        )

    async def prepare_application_package(
        self,
        job_id: UUID,
        resume_profile_id: UUID,
        candidate_profile_id: UUID | None = None,
    ) -> ToolResult:
        """Prepare a full application package (mutating, gate-checked)."""
        self._require_write_access()
        profile = await self._ctx.candidate_service.resolve_profile(candidate_profile_id)
        job = await self._ctx.job_repository.get(job_id)
        if not job:
            raise McpToolError(f"Job {job_id} not found")
        match = await self._ctx.match_repository.get_by_job_and_candidate(job_id, profile.id)
        if not match:
            await self._ctx.matching_service.analyze_job(job_id, profile.id)
            match = await self._ctx.match_repository.get_by_job_and_candidate(job_id, profile.id)
        decision = self._gate.evaluate(
            self._build_context("prepare_application_package", job, match, profile)
        )
        if decision.status == ApprovalStatus.DENIED:
            raise McpToolError(f"Action denied: {decision.reason}")

        application = await self._ctx.application_service.create(
            job_id=job_id,
            candidate_profile_id=profile.id,
            resume_profile_id=resume_profile_id,
        )
        await self._ctx.application_service.build_package(getattr(application, "id", None))
        return ToolResult(
            tool="prepare_application_package",
            data={
                "application_id": str(getattr(application, "id", "?")),
                "approval": decision.to_dict(),
            },
        )

    async def update_application_status(
        self,
        application_id: UUID,
        status: str,
        candidate_profile_id: UUID | None = None,
    ) -> ToolResult:
        """Update the status of an application (mutating, gate-checked)."""
        self._require_write_access()
        decision = self._gate.evaluate(
            self._build_update_context(
                "update_application_status",
                type(
                    "App",
                    (),
                    {
                        "id": application_id,
                        "job_id": None,
                        "candidate_profile_id": candidate_profile_id,
                    },
                )(),
            )
        )
        if decision.status == ApprovalStatus.DENIED:
            raise McpToolError(f"Action denied: {decision.reason}")
        await self._ctx.application_service.update_status(application_id, status)
        return ToolResult(
            tool="update_application_status",
            data={
                "application_id": str(application_id),
                "status": status,
                "approval": decision.to_dict(),
            },
        )

    async def list_applications(
        self,
        status_filter: str | None = None,
        candidate_profile_id: UUID | None = None,
    ) -> ToolResult:
        """List the candidate's applications, optionally filtered by status."""
        self._gate.can_read()
        profile = await self._ctx.candidate_service.resolve_profile(candidate_profile_id)
        applications = await self._ctx.application_service.list_by_candidate(
            profile.id, status_filter=status_filter
        )
        return ToolResult(
            tool="list_applications",
            data={"applications": [str(getattr(a, "id", "?")) for a in applications]},
        )

    async def recalculate_match(
        self, job_id: UUID, candidate_profile_id: UUID | None = None
    ) -> ToolResult:
        """Force re-analysis of a job against the candidate profile."""
        self._gate.can_read()
        result = await self._ctx.matching_service.analyze_job(job_id, candidate_profile_id)
        return ToolResult(
            tool="recalculate_match",
            data={
                "score": getattr(result, "score", 0),
                "recommendation": getattr(result, "recommendation", "UNKNOWN"),
            },
        )

    async def get_application_history(self, application_id: UUID) -> ToolResult:
        """Get the status history of an application (read-only)."""
        self._gate.can_read()
        history = await self._ctx.application_service.get_status_history(application_id)
        return ToolResult(
            tool="get_application_history",
            data={"history": history},
        )

    async def get_feedback_stats(self, candidate_profile_id: UUID | None = None) -> ToolResult:
        """Get feedback statistics for the candidate (read-only)."""
        self._gate.can_read()
        profile = await self._ctx.candidate_service.resolve_profile(candidate_profile_id)
        stats = await self._ctx.feedback_service.feedback_report(profile.id)
        return ToolResult(tool="get_feedback_stats", data=stats)
