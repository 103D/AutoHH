# Scoring Model (match model v3)

This document defines the deterministic scoring model and answers the audit
questions from the refactoring task. The implementation lives in
`app/services/scoring/` (bounded components) and is orchestrated by
`app/services/matching.py` (pipeline only).

## Design goals

- **Deterministic**: the final number is pure Python — weights, thresholds,
  caps. No LLM output enters the arithmetic.
- **Explainable**: every vacancy result can answer "why 78 and not 90?" via
  `score_breakdown` (component scores + per-skill requirement audit + caps +
  LLM adjustments).
- **Requirement-oriented**: the technical score measures *how well the
  candidate covers the job's requirements*, not the legacy inverted metric
  (*how many of the candidate's skills appear in the ad*).

## Skill requirement model

Each vacancy yields a list of skill requirements classified by importance:

| Importance | Meaning | Weight (default) |
|------------|---------|------------------|
| `REQUIRED` | mandatory; absence is always visible | 3.0 |
| `PREFERRED` | strong plus | 1.5 |
| `OPTIONAL` | nice-to-have / generic mention | 0.5 |

Each requirement gets a match status against the candidate profile:

| Status | Value | Meaning |
|--------|-------|---------|
| `MATCHED` | 1.0 | exact / alias via taxonomy / variant spelled in a longer form |
| `PARTIAL` | 0.5 | transferable / LLM-equivalent / conservative related match |
| `MISSING` | 0.0 | candidate does not have the skill |
| `UNKNOWN` | — | no candidate skill data; excluded from the denominator |

## Technical score

```
technical = 100 * Σ(w_i * value_i) / Σ(w_i)      over judged requirements
```

`UNKNOWN` requirements are excluded from both sums (no data to judge) but stay
visible in the breakdown. A missing REQUIRED keeps its full weight in the
denominator — so it always drags the score down.

If no requirements can be extracted at all, the engine falls back to the legacy
candidate-coverage heuristic and flags it via `skills.source == "heuristic"`.

## Aggregation

```
raw   = Σ(component_score * component_weight)     (weights normalized to 1.0)
cap   = 100 - (n_missing_required * SCORE_MISSING_REQUIRED_PENALTY)
final = clamp(min(raw, cap), 0, 100)
```

The cap is a **soft** penalty, not a hard blocker: the score is lowered and the
missing skills are listed in `score_caps` + `skills.missing_required`, but the
vacancy is not auto-rejected. (Hard rejection is only via `HardFilterEngine`.)

## LLM boundary

The LLM performs **semantic interpretation only**:

- extract requirements, classify required/preferred;
- normalize technologies, identify equivalents / transferable skills;
- seniority / domain signals; explain gaps.

Python owns: hard filters, numeric scoring, weights, thresholds, the final
score and the recommendation. `ScoringEngine.apply_llm_requirements` re-runs
the deterministic machinery on the LLM-extracted requirements; the LLM's own
`score` field is **never** used in the final number. Any change is recorded in
`score_breakdown.llm_adjustments`.

## Audit answers (task §2)

1. **What is the technical score?** Weighted requirement coverage (above) —
   the share of the job's weighted requirements the candidate satisfies.
2. **REQUIRED vs PREFERRED?** Yes — different importance classes with weights
   3.0 / 1.5 / 0.5 (`SCORE_*_SKILL_WEIGHT`).
3. **High score with a critically missing skill?** Bounded: each missing
   REQUIRED applies a soft cap (`100 - N*25` by default) and is listed
   separately, so it cannot hide inside a high aggregate.
4. **Different skill weights?** Yes, by importance class (see table).
5. **Seniority?** Via the experience component (years/seniority) and the
   stretch classifier; `job.experience_required` is used.
6. **Domain experience?** Domain enters via specialization (resume selection /
   stretch), not as a hidden score term.
7. **Specialization?** Affects recommendation / resume selection, not the base
   score. A vacancy may have several specializations; the best profile wins.
8. **Can location/salary compensate technical?** Only up to the missing-
   REQUIRED cap; location/salary weights (0.10 each) cannot lift a vacancy past
   the cap when a mandatory skill is missing.
9. **Can the LLM score fix a bad deterministic score?** No — the LLM score is
   ignored; only LLM-*semantics* (requirements/equivalents) re-run through the
   deterministic formula can change the number, and every change is logged.
10. **Upper/lower bounds?** Yes — explicit clamp to `[0, 100]` in `aggregate`.
    On `NOT_ELIGIBLE` the persisted score is forced to `0` in all paths.

## Hard filters

`HardFilterEngine` applies only objective constraints (experience, location /
relocation, work format, employment type, salary). The experience rule is a
documented, configurable business rule:

```
max_allowed = max(years * HARD_EXPERIENCE_MAX_FACTOR,
                  years + HARD_EXPERIENCE_MAX_GAP)
fail if required > max_allowed
```

The `MAX_GAP` buffer exists so a candidate with 0 documented years is not
silently blocked from every vacancy (0 × factor = 0). See `env.example`.
