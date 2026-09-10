"""Configuration helpers for Hermes — build config + policy from settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings
from app.hermes.modes import AutonomyMode
from app.hermes.policy import UserPolicy

if TYPE_CHECKING:
    from app.hermes.orchestrator import HermesConfig


def build_policy_from_settings() -> UserPolicy:
    """Build a UserPolicy from the hermes_policy_* settings."""
    return UserPolicy(
        min_score=settings.hermes_policy_min_score,
        min_salary_max=settings.hermes_policy_min_salary_max,
        max_salary_max=settings.hermes_policy_max_salary_max,
        locations=_csv(settings.hermes_policy_locations),
        specializations=_csv(settings.hermes_policy_specializations),
        excluded_companies=_csv(settings.hermes_policy_excluded_companies),
        employment_types=_csv(settings.hermes_policy_employment_types),
        work_formats=_csv(settings.hermes_policy_work_formats),
        max_experience_gap_years=settings.hermes_policy_max_experience_gap_years,
        allow_top_tier_companies=settings.hermes_policy_allow_top_tier,
    )


def build_hermes_config_from_settings(gpt55_provider=None) -> HermesConfig:
    """Build HermesConfig (mode + policy + gate) from environment settings."""
    from app.hermes.approval_gate import ActionGate
    from app.hermes.orchestrator import HermesConfig

    mode = AutonomyMode.from_str(settings.hermes_mode)
    policy = build_policy_from_settings()
    gate = ActionGate(mode=mode, policy=policy, auto_approve_review_threshold=settings.hermes_auto_approve_review_threshold)
    return HermesConfig(
        mode=mode,
        policy=policy,
        gpt55_provider=gpt55_provider,
        action_gate=gate,
    )


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
