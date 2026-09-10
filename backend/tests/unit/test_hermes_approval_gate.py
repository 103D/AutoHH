"""Tests for ActionGate evaluation across all modes and contexts."""

import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from app.hermes.approval_gate import (
    ActionContext,
    ActionDecision,
    ActionGate,
    ActionType,
    ApprovalStatus,
)
from app.hermes.modes import AutonomyMode
from app.hermes.policy import UserPolicy


class _FakeJob:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid4())
        self.title = kwargs.get("title", "Data Analyst")
        self.company = kwargs.get("company", "TestCo")
        self.location = kwargs.get("location", "Москва")
        self.salary_min = kwargs.get("salary_min", 100000)
        self.salary_max = kwargs.get("salary_max", 200000)
        self.currency = kwargs.get("currency", "RUB")
        self.employment_type = kwargs.get("employment_type", "full_time")
        self.work_format = kwargs.get("work_format", "remote")
        self.experience_required = kwargs.get("experience_required", 3)
        self.specializations = kwargs.get("specializations", ["DATA_ANALYST"])
        self.description = kwargs.get("description", "")


class _FakeMatch:
    def __init__(self, score=80):
        self.score = score


class _FakeProfile:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid4())
        self.experience_years = kwargs.get("experience_years", 3)
        self.experience_level = kwargs.get("experience_level", "middle")
        self.desired_salary_min = kwargs.get("desired_salary_min", 100000)
        self.desired_salary_max = kwargs.get("desired_salary_max", 200000)
        self.location = kwargs.get("location", "Москва")
        self.employment_types = kwargs.get("employment_types", ["full_time"])
        self.work_formats = kwargs.get("work_formats", ["remote"])
        self.skills = kwargs.get("skills", ["sql", "python"])


def _ctx(action, job=None, match=None, profile=None, **kwargs):
    return ActionContext(
        action=action,
        job_id=job.id if job else None,
        candidate_profile_id=profile.id if profile else None,
        match_score=match.score if match else None,
        job=job,
        match=match,
        profile=profile,
        **kwargs,
    )


class TestActionGateReadOnly:
    def test_read_only_denies_all_mutations(self):
        gate = ActionGate(AutonomyMode.READ_ONLY, UserPolicy())
        for action in ActionType:
            decision = gate.evaluate(_ctx(action))
            assert decision.status == ApprovalStatus.DENIED
            assert "READ_ONLY" in decision.reason

    def test_read_only_can_read(self):
        gate = ActionGate(AutonomyMode.READ_ONLY, UserPolicy())
        assert gate.can_read() is True

    def test_read_only_cannot_mutate(self):
        gate = ActionGate(AutonomyMode.READ_ONLY, UserPolicy())
        assert gate.can_mutate() is False


class TestActionGateAssisted:
    def test_assisted_requires_approval_for_mutations(self):
        gate = ActionGate(AutonomyMode.ASSISTED, UserPolicy())
        for action in ActionType:
            decision = gate.evaluate(_ctx(action))
            assert decision.status == ApprovalStatus.PENDING_APPROVAL
            assert decision.requires_review is True
            assert "ASSISTED" in decision.reason

    def test_assisted_can_read(self):
        gate = ActionGate(AutonomyMode.ASSISTED, UserPolicy())
        assert gate.can_read() is True

    def test_assisted_can_mutate_flag(self):
        gate = ActionGate(AutonomyMode.ASSISTED, UserPolicy())
        assert gate.can_mutate() is True


class TestActionGateAutonomousNoContext:
    def test_autonomous_without_job_context_approves(self):
        gate = ActionGate(AutonomyMode.AUTONOMOUS, UserPolicy())
        decision = gate.evaluate(_ctx(ActionType.RECORD_FEEDBACK))
        assert decision.status == ApprovalStatus.APPROVED
        assert decision.requires_review is False


class TestActionGateAutonomousWithPolicy:
    def test_autonomous_job_satisfying_policy_approves(self):
        policy = UserPolicy(min_score=70)
        gate = ActionGate(AutonomyMode.AUTONOMOUS, policy)
        decision = gate.evaluate(_ctx(
            ActionType.CREATE_APPLICATION,
            job=_FakeJob(),
            match=_FakeMatch(score=85),
            profile=_FakeProfile(),
        ))
        assert decision.status == ApprovalStatus.APPROVED
        assert decision.requires_review is False

    def test_autonomous_job_failing_policy_denies(self):
        policy = UserPolicy(min_score=80)
        gate = ActionGate(AutonomyMode.AUTONOMOUS, policy)
        decision = gate.evaluate(_ctx(
            ActionType.CREATE_APPLICATION,
            job=_FakeJob(),
            match=_FakeMatch(score=60),
            profile=_FakeProfile(),
        ))
        assert decision.status == ApprovalStatus.DENIED
        assert decision.requires_review is True
        assert len(decision.policy_violations) > 0

    def test_autonomous_high_score_overrides_policy_failure(self):
        policy = UserPolicy(min_score=80)
        gate = ActionGate(
            AutonomyMode.AUTONOMOUS, policy, auto_approve_review_threshold=70
        )
        decision = gate.evaluate(_ctx(
            ActionType.CREATE_APPLICATION,
            job=_FakeJob(),
            match=_FakeMatch(score=75),
            profile=_FakeProfile(),
        ))
        # score 75 >= 70 but < 80 policy min → APPROVED with review
        assert decision.status == ApprovalStatus.APPROVED
        assert decision.requires_review is True
        assert len(decision.policy_violations) > 0

    def test_autonomous_low_score_failing_policy_denies(self):
        policy = UserPolicy(min_score=80, locations=["Москва"])
        gate = ActionGate(
            AutonomyMode.AUTONOMOUS, policy, auto_approve_review_threshold=70
        )
        decision = gate.evaluate(_ctx(
            ActionType.CREATE_APPLICATION,
            job=_FakeJob(location="Казань"),
            match=_FakeMatch(score=65),
            profile=_FakeProfile(),
        ))
        assert decision.status == ApprovalStatus.DENIED
        assert decision.requires_review is True


class TestActionGateDecisionSerialization:
    def test_action_decision_to_dict(self):
        decision = ActionDecision(
            status=ApprovalStatus.DENIED,
            action=ActionType.CREATE_APPLICATION,
            reason="test reason",
            policy_violations=["violation1"],
            requires_review=True,
        )
        d = decision.to_dict()
        assert d["status"] == "DENIED"
        assert d["action"] == "create_application"
        assert d["reason"] == "test reason"
        assert d["policy_violations"] == ["violation1"]
        assert d["requires_review"] is True
        assert "decided_at" in d


class TestActionGateFromMode:
    def test_gate_uses_mode_from_string(self):
        gate = ActionGate("AUTONOMOUS", UserPolicy())
        assert gate.mode == AutonomyMode.AUTONOMOUS

    def test_gate_uses_mode_from_enum(self):
        gate = ActionGate(AutonomyMode.ASSISTED, UserPolicy())
        assert gate.mode == AutonomyMode.ASSISTED


class TestActionGateMultipleActions:
    def test_each_action_type_produces_decision(self):
        gate = ActionGate(AutonomyMode.AUTONOMOUS, UserPolicy())
        for action in ActionType:
            decision = gate.evaluate(_ctx(action))
            assert decision.status in (
                ApprovalStatus.APPROVED,
                ApprovalStatus.DENIED,
                ApprovalStatus.PENDING_APPROVAL,
            )
            assert decision.action == action
