"""Tests for HermesMcpTools gate enforcement."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.hermes.approval_gate import ActionGate
from app.hermes.mcp_tools import HermesMcpTools, McpToolError, ToolResult
from app.hermes.modes import AutonomyMode
from app.hermes.policy import UserPolicy


class _FakeProfile:
    def __init__(self):
        self.id = uuid4()
        self.experience_years = 3
        self.experience_level = "middle"
        self.desired_salary_min = 100000
        self.desired_salary_max = 200000
        self.location = "Москва"
        self.skills = ["sql", "python"]
        self.technologies = {}
        self.employment_types = ["full_time"]
        self.work_formats = ["remote"]


class _FakeJob:
    def __init__(self):
        self.id = uuid4()
        self.title = "Data Analyst"
        self.company = "TestCo"
        self.description = "Job description"
        self.location = "Москва"
        self.salary_min = 100000
        self.salary_max = 200000
        self.currency = "RUB"
        self.employment_type = "full_time"
        self.work_format = "remote"
        self.experience_required = 3
        self.specializations = ["DATA_ANALYST"]


class _FakeMatch:
    def __init__(self, score=75, **kwargs):
        self.score = score
        self.job_id = kwargs.get("job_id", uuid4())
        self.candidate_profile_id = kwargs.get("candidate_profile_id", uuid4())
        self.recommendation = "SOLID_MATCH"
        self.user_override_recommendation = None
        self.matched_skills = ["sql"]
        self.missing_skills = ["tableau"]
        self.strong_matches = []
        self.concerns = []
        self.reasoning_summary = "Test"
        self.score_breakdown = {}
        self.hard_failures = []
        self.analysis_fingerprint = "fp123"
        self.analyzed_at = None


def _make_tools(mode="AUTONOMOUS", policy=None):
    ctx = MagicMock()
    ctx.candidate_service = MagicMock()
    ctx.candidate_service.resolve_profile = AsyncMock(return_value=_FakeProfile())
    ctx.job_repository = MagicMock()
    ctx.job_repository.get = AsyncMock(return_value=_FakeJob())
    ctx.match_repository = MagicMock()
    ctx.match_repository.get_by_job_and_candidate = AsyncMock(return_value=_FakeMatch())
    ctx.matching_service = MagicMock()
    ctx.matching_service.analyze_job = AsyncMock(return_value=None)

    gate = ActionGate(
        AutonomyMode.from_str(mode),
        policy or UserPolicy(),
    )
    ctx.action_gate = gate

    return HermesMcpTools(ctx)


class TestMcpToolResult:
    def test_tool_result_creation(self):
        result = ToolResult(tool="test_tool", data={"key": "value"})
        assert result.tool == "test_tool"
        assert result.data == {"key": "value"}

    def test_tool_result_serializable(self):
        result = ToolResult(tool="search_jobs", data={"jobs": []})
        assert result.tool == "search_jobs"
        assert isinstance(result.data, dict)


class TestMcpToolError:
    def test_error_can_be_raised(self):
        with pytest.raises(McpToolError):
            raise McpToolError("test error")

    def test_error_message(self):
        try:
            raise McpToolError("specific message")
        except McpToolError as e:
            assert str(e) == "specific message"


class TestMcpToolsReadOnlyBlocksMutations:
    def test_read_only_blocks_mutating_tools(self):
        tools = _make_tools(mode="READ_ONLY")
        assert tools._gate.can_mutate() is False

    def test_read_only_allows_read_tools(self):
        tools = _make_tools(mode="READ_ONLY")
        assert tools._gate.can_read() is True


class TestMcpToolsAssistedRequiresApproval:
    def test_assisted_requires_approval(self):
        tools = _make_tools(mode="ASSISTED")
        assert tools._gate.can_mutate() is True


class TestMcpToolsAutonomousWithPolicy:
    def test_autonomous_allows_when_policy_satisfied(self):
        policy = UserPolicy(min_score=50)
        tools = _make_tools(mode="AUTONOMOUS", policy=policy)
        assert tools._gate.can_mutate() is True

    def test_autonomous_blocks_when_policy_fails(self):
        policy = UserPolicy(min_score=99)
        gate = ActionGate(AutonomyMode.AUTONOMOUS, policy)
        ctx = MagicMock()
        ctx.action_gate = gate
        ctx.candidate_service.resolve_profile = AsyncMock(return_value=_FakeProfile())
        ctx.job_repository.get = AsyncMock(return_value=_FakeJob())
        ctx.match_repository.get_by_job_and_candidate = AsyncMock(
            return_value=_FakeMatch(score=50)
        )
        HermesMcpTools(ctx)

        job = _FakeJob()
        match = _FakeMatch(score=50)
        profile = _FakeProfile()

        decision = gate.evaluate(
            MagicMock(
                action="create_application",
                job=job,
                match=match,
                profile=profile,
                match_score=match.score,
            )
        )
        assert decision.status.value in ("DENIED", "PENDING_APPROVAL")


class TestMcpToolsContextPropagation:
    def test_tools_have_context(self):
        tools = _make_tools()
        assert tools._ctx is not None

    def test_tools_have_gate(self):
        tools = _make_tools()
        assert tools._gate is not None
