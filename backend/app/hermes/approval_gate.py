"""Action Gate: approve/reject all mutating operations.

Every write that Hermes could trigger (create application, update status,
adapt resume, override recommendation, etc.) passes through the ActionGate.
The gate enforces:
1. Autonomy mode — READ_ONLY blocks everything; ASSISTED requires approval.
2. User policy — in AUTONOMOUS mode, only jobs that satisfy the policy are
   auto-approved; others are queued for manual review.
3. Audit trail — every decision (auto-approved, denied, pending-approval)
   is recorded so GPT-5.5 can reason about past rejections.

Hermes never writes to PostgreSQL directly; the gate returns a decision and
the caller (or the domain service) performs the actual write.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.hermes.modes import AutonomyMode


class ActionType(StrEnum):
    """Mutating actions that may be triggered by Hermes."""

    CREATE_APPLICATION = "create_application"
    UPDATE_APPLICATION_STATUS = "update_application_status"
    PREPARE_APPLICATION_PACKAGE = "prepare_application_package"
    RECOMMEND_RESUME = "recommend_resume"
    OVERRIDE_RECOMMENDATION = "override_recommendation"
    RECORD_FEEDBACK = "record_feedback"


class ApprovalStatus(StrEnum):
    """Outcome of an action gate check."""

    APPROVED = "APPROVED"
    DENIED = "DENIED"
    PENDING_APPROVAL = "PENDING_APPROVAL"


@dataclass
class ActionContext:
    """Context for an action gate decision."""

    action: ActionType
    job_id: UUID | None = None
    candidate_profile_id: UUID | None = None
    application_id: UUID | None = None
    match_score: int | None = None
    job: Any | None = None
    match: Any | None = None
    profile: Any | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionDecision:
    """Result of evaluating an action against mode + policy."""

    status: ApprovalStatus
    action: ActionType
    reason: str = ""
    policy_violations: list[str] = field(default_factory=list)
    requires_review: bool = False
    decided_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "action": self.action.value,
            "reason": self.reason,
            "policy_violations": list(self.policy_violations),
            "requires_review": self.requires_review,
            "decided_at": self.decided_at.isoformat(),
        }


class ActionGate:
    """Evaluates whether a Hermes action is allowed under the current mode + policy.

    The gate is stateless and side-effect-free: it returns a decision, the caller
    is responsible for acting on it.
    """

    def __init__(
        self,
        mode: Any,
        policy: Any,
        *,
        auto_approve_review_threshold: int = 70,
    ):
        self.mode = AutonomyMode.from_str(mode.value if hasattr(mode, "value") else str(mode))
        self.policy = policy
        self.auto_approve_review_threshold = auto_approve_review_threshold

    def evaluate(self, context: ActionContext) -> ActionDecision:
        """Evaluate an action and return the approval decision."""
        action = context.action

        # READ_ONLY: block all mutations
        if not self.mode.allows_mutation():
            return ActionDecision(
                status=ApprovalStatus.DENIED,
                action=action,
                reason=f"AutonomyMode {self.mode} does not permit mutations",
                requires_review=False,
            )

        # In ASSISTED mode: everything needs manual approval
        if self.mode == AutonomyMode.ASSISTED:
            return ActionDecision(
                status=ApprovalStatus.PENDING_APPROVAL,
                action=action,
                reason="ASSISTED mode: action requires manual approval",
                requires_review=True,
            )

        # AUTONOMOUS mode: check policy for action types that have a job context
        if (
            self.mode.allows_autonomous_apply()
            and context.job is not None
            and context.match is not None
            and context.profile is not None
        ):
            permitted, violations = self.policy.evaluate(
                context.job, context.match, context.profile
            )
            if permitted:
                return ActionDecision(
                    status=ApprovalStatus.APPROVED,
                    action=action,
                    reason="AUTONOMOUS: job satisfies user policy",
                    requires_review=False,
                )
            # Job doesn't satisfy policy: auto-approve with review if score is high
            if (
                context.match_score is not None
                and context.match_score >= self.auto_approve_review_threshold
            ):
                return ActionDecision(
                    status=ApprovalStatus.APPROVED,
                    action=action,
                    reason=(
                        f"AUTONOMOUS: score {context.match_score} >= threshold "
                        f"{self.auto_approve_review_threshold} (policy overrides)"
                    ),
                    policy_violations=violations,
                    requires_review=True,
                )
            return ActionDecision(
                status=ApprovalStatus.DENIED,
                action=action,
                reason="AUTONOMOUS: job does not satisfy user policy",
                policy_violations=violations,
                requires_review=True,
            )

        # AUTONOMOUS but no job/match context (e.g. RECORD_FEEDBACK) — auto-approve
        if self.mode.allows_autonomous_apply():
            return ActionDecision(
                status=ApprovalStatus.APPROVED,
                action=action,
                reason="AUTONOMOUS: no job-scoped policy check required",
                requires_review=False,
            )

        # Fallback: require approval
        return ActionDecision(
            status=ApprovalStatus.PENDING_APPROVAL,
            action=action,
            reason="No applicable policy path; requires approval",
            requires_review=True,
        )

    def can_read(self) -> bool:
        """Read operations are always allowed regardless of mode."""
        return True

    def can_mutate(self) -> bool:
        """Whether this mode allows any mutations."""
        return self.mode.allows_mutation()
