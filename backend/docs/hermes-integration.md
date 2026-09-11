# Hermes + GPT-5.5 Integration

Hermes is the MCP (Model Context Protocol) tool layer between GPT-5.5 and the
AutoHH domain. It enforces a strict boundary:

> **GPT-5.5 thinks. Hermes orchestrates. AutoHH executes. PostgreSQL stores.**

GPT-5.5 never touches PostgreSQL, OAuth tokens, or cookies. It only reasons
about which tools to call. Hermes executes the calls and enforces the action
gate. AutoHH domain services perform the actual work.

## Architecture

```
User Goal (natural language)
        │
        ▼
┌─────────────────────────────────────────────┐
│  HermesOrchestrator                         │
│  ├─ GPT-5.5 reasoning (reasoning_provider)  │
│  ├─ Tool execution (mcp_tools)              │
│  └─ Action gate (approval_gate + policy)    │
└──────────────┬──────────────────────────────┘
               │ delegates to
               ▼
┌─────────────────────────────────────────────┐
│  AutoHH Domain Services                     │
│  ├─ MatchingService (scoring, hard filters) │
│  ├─ CandidateService (profiles)             │
│  ├─ JobRepository, MatchResultRepository    │
│  └─ ApplicationService, FeedbackService     │
└──────────────┬──────────────────────────────┘
               │ writes to
               ▼
           PostgreSQL
```

## Modules

| Module | Purpose |
|--------|---------|
| `modes.py` | `AutonomyMode` enum: READ_ONLY, ASSISTED, AUTONOMOUS |
| `policy.py` | `UserPolicy` — declarative guardrails for autonomous actions |
| `approval_gate.py` | `ActionGate` — approve/reject every mutating operation |
| `mcp_tools.py` | `HermesMcpTools` — MCP tool surface with gate enforcement |
| `orchestrator.py` | `HermesOrchestrator` — main reasoning → tool execution loop |
| `reasoning_provider.py` | `GPT55ReasoningProvider` — reasoning-only, never scores |
| `gap_analysis_service.py` | `HermesGapAnalysisService` — deterministic gap analysis |
| `config.py` | Build `UserPolicy` + `HermesConfig` from settings |

## Autonomy Modes

| Mode | Read | Mutate | Auto-Apply |
|------|------|--------|------------|
| `READ_ONLY` | ✅ | ❌ | ❌ |
| `ASSISTED` | ✅ | ✅ (requires approval) | ❌ |
| `AUTONOMOUS` | ✅ | ✅ | ✅ (when policy satisfied) |

## User Policy Guardrails

All fields optional — unset guards are not evaluated. AND semantics.

```python
policy = UserPolicy(
    min_score=60,
    min_salary_max=150_000,
    locations=["Москва", "Алматы"],
    specializations=["DATA_ANALYST", "BI_ANALYST"],
    excluded_companies=["bad_corp"],
    max_experience_gap_years=2.0,
    employment_types=["full_time"],
    work_formats=["remote", "hybrid"],
)
```

In `AUTONOMOUS` mode:
- If job satisfies policy → **APPROVED** (auto-submit)
- If job fails policy + score ≥ threshold (default 70) → **APPROVED** with review flag
- If job fails policy + score < threshold → **DENIED**

## Action Types

```python
class ActionType(str, Enum):
    CREATE_APPLICATION = "create_application"
    UPDATE_APPLICATION_STATUS = "update_application_status"
    PREPARE_APPLICATION_PACKAGE = "prepare_application_package"
    RECOMMEND_RESUME = "recommend_resume"
    OVERRIDE_RECOMMENDATION = "override_recommendation"
    RECORD_FEEDBACK = "record_feedback"
```

## LLM Boundary (match model v3, preserved)

GPT-5.5 provides **semantic interpretation only**:
- Required vs preferred skills, equivalences, transferable skills
- Seniority/domain signals, risks, concerns
- Never assigns a numeric score

The deterministic `ScoringEngine` inside AutoHH always computes the final
score. The LLM's `score` field in responses is advisory and overridden.

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `hermes_mode` | `READ_ONLY` | Autonomy mode |
| `hermes_policy_min_score` | 50 | Min match score for auto-apply |
| `hermes_policy_min_salary_max` | None | Min salary_max for auto-apply |
| `hermes_policy_max_salary_max` | None | Max salary_max for auto-apply |
| `hermes_policy_locations` | None | CSV of allowed locations |
| `hermes_policy_specializations` | None | CSV of allowed specializations |
| `hermes_policy_excluded_companies` | None | CSV of excluded companies |
| `hermes_policy_employment_types` | None | CSV of allowed employment types |
| `hermes_policy_work_formats` | None | CSV of allowed work formats |
| `hermes_policy_max_experience_gap_years` | None | Max experience gap |
| `hermes_policy_allow_top_tier` | False | Allow top-tier companies |
| `hermes_auto_approve_review_threshold` | 70 | Score threshold for auto-approve-with-review |
| `hermes_gpt_api_key` | None | GPT-5.5 API key |
| `hermes_gpt_model` | `gpt-5.5-turbo` | Model name |
| `hermes_gpt_max_tokens` | 2048 | Max tokens |
| `hermes_gpt_temperature` | 0.3 | Temperature |
| `hermes_gpt_base_url` | OpenAI URL | API base URL |

## HermesConfig Assembly

```python
from app.hermes.config import build_hermes_config_from_settings

config = build_hermes_config_from_settings()
# Returns HermesConfig(mode, policy, gpt55_provider, action_gate)
```

## Running Tests

```bash
poetry run pytest tests/unit/test_hermes_*.py -v
# 88 tests covering modes, policy, gate, gap analysis, MCP tools, orchestrator
```
