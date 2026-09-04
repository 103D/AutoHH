"""ScoringEngine — deterministic scoring orchestration (match model v3).

Public API (unchanged):
    engine = ScoringEngine(weights=...)           # weights normalized to 1.0
    score, breakdown = engine.calculate(cand, job)
    engine.calculate_<component>_score(cand, job)
    engine.get_recommendation(score)

Aggregation is explicit: component scores are a weighted average, then a soft
cap is applied for missing REQUIRED skills (visible in ``score_caps``), then
the result is clamped to [0, 100]. LLM output never enters the math here —
``apply_llm_requirements`` only re-runs the deterministic machinery on
LLM-extracted semantics and is called by the MatchingService.
"""

from typing import Any

from app.core.config import settings
from app.models.candidate import CandidateProfile
from app.models.job import Job
from app.models.matching import MatchCategory
from app.services.scoring import education_language as edu
from app.services.scoring import experience as exp
from app.services.scoring import location as loc
from app.services.scoring import salary as sal
from app.services.scoring import work_format as wf
from app.services.scoring.model import ScoreBreakdown, SkillAudit
from app.services.scoring.skills import (
    SKILL_STOPWORDS,
    analyze_technical,
    choose_importance_weights,
    re_score_from_llm,
    score_requirements,
)
from app.services.scoring.tokenize import normalize_skills, tokenize_text


class ScoringEngine:
    """Calculate deterministic match scores between jobs and candidates."""

    STOPWORDS = SKILL_STOPWORDS

    def __init__(self, weights: dict[str, float] | None = None):
        """Build the engine with configurable weights (task spec #9).

        Defaults come from settings (SCORE_WEIGHT_* env vars); an explicit
        ``weights`` override (e.g. a per-candidate MatchingProfile) takes
        precedence. The final weights are always normalized to sum to 1.0.
        """
        resolved = {
            "technical": settings.score_weight_technical,
            "experience": settings.score_weight_experience,
            "location": settings.score_weight_location,
            "salary": settings.score_weight_salary,
            "work_format": settings.score_weight_work_format,
            "education": settings.score_weight_education,
            "language": settings.score_weight_language,
        }
        if weights:
            unknown = set(weights) - set(resolved)
            if unknown:
                raise ValueError(f"Unknown scoring weights: {sorted(unknown)}")
            resolved.update(
                {k: float(v) for k, v in weights.items() if v is not None}
            )
        total = sum(resolved.values())
        if total <= 0:
            raise ValueError("Scoring weights must sum to a positive value")
        self.weights = {k: v / total for k, v in resolved.items()}
        # REQUIRED/PREFERRED/OPTIONAL weights inside the technical component.
        self.importance_weights = choose_importance_weights()

    # --- public helpers (also kept as underscore aliases for older callers) ---

    def tokenize_text(self, text: str | None) -> set[str]:
        return tokenize_text(text)

    def normalize_skills(self, value: Any) -> set[str]:
        return normalize_skills(value)

    _tokenize_text = tokenize_text
    _normalize_skills = normalize_skills

    # --- candidate helpers ---

    @staticmethod
    def candidate_skills(candidate: CandidateProfile) -> set[str]:
        """Lowercased union of candidate skills + technologies."""
        return normalize_skills(candidate.skills) | normalize_skills(
            candidate.technologies
        )

    # --- component scores (public, per-test contract) ---

    def calculate_technical_score(self, candidate: CandidateProfile, job: Job) -> float:
        return self.analyze_technical(candidate, job)[0]

    def analyze_technical(
        self, candidate: CandidateProfile, job: Job
    ) -> tuple[float, SkillAudit]:
        """Technical score + explainability audit (skill requirements v3)."""
        cand = self.candidate_skills(candidate)
        score, audit = analyze_technical(cand, job)
        if audit.source != "heuristic":
            # Recompute with the engine's configured importance weights.
            score = score_requirements(audit.requirements, self.importance_weights)
        return score, audit

    def calculate_experience_score(self, candidate: CandidateProfile, job: Job) -> float:
        return exp.experience_score(candidate, job)

    def calculate_location_score(self, candidate: CandidateProfile, job: Job) -> float:
        return loc.location_score(candidate, job)

    def calculate_salary_score(self, candidate: CandidateProfile, job: Job) -> float:
        return sal.salary_score(candidate, job)

    def calculate_work_format_score(self, candidate: CandidateProfile, job: Job) -> float:
        return wf.work_format_score(candidate, job)

    def calculate_education_score(self, candidate: CandidateProfile, job: Job) -> float:
        return edu.education_score(candidate, job)

    def calculate_language_score(self, candidate: CandidateProfile, job: Job) -> float:
        return edu.language_score(candidate, job)

    # --- aggregation ---

    def aggregate(self, breakdown: ScoreBreakdown) -> float:
        """Weighted sum + soft cap for missing REQUIRED skills + clamp."""
        raw = (
            breakdown.technical * self.weights["technical"]
            + breakdown.experience * self.weights["experience"]
            + breakdown.location * self.weights["location"]
            + breakdown.salary * self.weights["salary"]
            + breakdown.work_format * self.weights["work_format"]
            + breakdown.education * self.weights["education"]
            + breakdown.language * self.weights["language"]
        )
        final = raw

        missing_required = (
            breakdown.skills.missing_required if breakdown.skills else []
        )
        if missing_required:
            penalty = settings.score_missing_required_penalty * len(
                missing_required
            )
            cap = 100.0 - penalty
            if final > cap:
                breakdown.score_caps.append(
                    {
                        "reason": (
                            f"{len(missing_required)} missing required skill(s): "
                            f"{', '.join(missing_required)}"
                        ),
                        "cap": round(cap, 1),
                    }
                )
                final = cap

        return round(min(max(final, 0.0), 100.0), 1)

    def calculate(
        self, candidate: CandidateProfile, job: Job
    ) -> tuple[float, ScoreBreakdown]:
        """Full deterministic score. Returns ``(final_score, breakdown)``."""
        breakdown = ScoreBreakdown()
        breakdown.technical, breakdown.skills = self.analyze_technical(
            candidate, job
        )
        breakdown.experience = self.calculate_experience_score(candidate, job)
        breakdown.location = self.calculate_location_score(candidate, job)
        breakdown.salary = self.calculate_salary_score(candidate, job)
        breakdown.work_format = self.calculate_work_format_score(candidate, job)
        breakdown.education = self.calculate_education_score(candidate, job)
        breakdown.language = self.calculate_language_score(candidate, job)

        final_score = self.aggregate(breakdown)
        return final_score, breakdown

    # --- LLM boundary: semantic interpretation only ---

    def apply_llm_requirements(
        self,
        ai_result: Any,
        candidate: CandidateProfile,
        breakdown: ScoreBreakdown,
    ) -> tuple[float | None, dict[str, Any] | None]:
        """Re-run deterministic scoring on LLM-extracted requirements.

        Returns ``(new_final_score, adjustments)`` or ``(None, None)`` when the
        LLM did not provide a requirement list (keep the deterministic result).
        The LLM never assigns a numeric score — it only refines the semantics.
        """
        requirements = list(getattr(ai_result, "requirements", None) or [])
        equivalences = list(
            getattr(ai_result, "skill_equivalences", None) or []
        )
        if not requirements and not equivalences:
            return None, None

        cand = self.candidate_skills(candidate)
        old_technical = breakdown.technical
        old_final = self.aggregate(breakdown)

        audit = re_score_from_llm(requirements, equivalences, cand)

        # No usable requirements from the LLM: keep the deterministic audit,
        # but still record the call for explainability.
        if not audit.requirements:
            return None, {
                "skills_override": False,
                "reason": "llm returned no usable requirements",
            }

        breakdown.skills = audit
        breakdown.technical = score_requirements(
            audit.requirements, self.importance_weights
        )
        new_final = self.aggregate(breakdown)
        adjustments = {
            "skills_override": True,
            "requirements_source": "llm",
            "technical_before": round(old_technical, 1),
            "technical_after": round(breakdown.technical, 1),
            "final_before": round(old_final, 1),
            "final_after": round(new_final, 1),
            "missing_required": list(audit.missing_required),
            "matched": list(audit.matched),
        }
        return new_final, adjustments

    def get_recommendation(self, score: float) -> str:
        """Map a numeric score to a match category (matching v2)."""
        if score >= settings.threshold_dream_job:
            return MatchCategory.DREAM_JOB
        elif score >= settings.threshold_stretch:
            return MatchCategory.STRETCH
        elif score >= settings.threshold_solid_match:
            return MatchCategory.SOLID_MATCH
        elif score >= settings.threshold_market_research:
            return MatchCategory.MARKET_RESEARCH
        elif score >= settings.threshold_learning:
            return MatchCategory.LEARNING_OPPORTUNITY
        return MatchCategory.IGNORE
