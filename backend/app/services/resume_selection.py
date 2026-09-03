"""Deterministic resume selection (task spec #16).

vacancy -> specializations -> matching resume profile -> best profile

No LLM involved: scores are fully reproducible and every recommendation
comes with human-readable reasons, e.g.::

    Recommended profile: Retail / Commercial Data Analyst
    Reason:
    - vacancy specialization: RETAIL_COMMERCIAL_ANALYST
    - title keywords: retail analytics
    - matched skills: SQL, PostgreSQL
"""

import re

from app.models.candidate import ResumeProfile
from app.models.job import Job
from app.schemas.resume import ResumeProfileScore, ResumeRecommendationResponse
from app.services.skill_taxonomy import skill_variants

# Deterministic scoring weights (not hardcoded across the codebase — one place)
WEIGHT_SPECIALIZATION = 50
WEIGHT_KEYWORD = 2  # per keyword hit; title hits count x3
WEIGHT_KEYWORD_CAP = 20
WEIGHT_SKILL = 5  # per selected skill found in the vacancy text
WEIGHT_SKILL_CAP = 20
# Below this the selector does not commit to a recommendation
MIN_RECOMMENDATION_SCORE = 10


def _contains_term(text: str, term: str) -> bool:
    """Word-boundary substring match ('bi' must not match inside 'mobile')."""
    if not term:
        return False
    return re.search(rf"(?<![a-zа-я0-9]){re.escape(term)}(?![a-zа-я0-9])", text) is not None


class ResumeSelector:
    """Picks the best resume profile for a vacancy and explains why."""

    def recommend(
        self, job: Job, profiles: list[ResumeProfile]
    ) -> ResumeRecommendationResponse:
        job_specializations = list(getattr(job, "specializations", None) or [])
        title = (job.title or "").lower()
        description = (job.description or "").lower()

        scored: list[ResumeProfileScore] = []
        for profile in profiles:
            if not profile.is_active:
                continue
            score, reasons = self._score_profile(
                profile, job_specializations, title, description
            )
            scored.append(
                ResumeProfileScore(
                    resume_profile_id=profile.id,
                    profile_name=profile.profile_name,
                    specialization=profile.specialization,
                    score=round(score, 1),
                    reasons=reasons,
                )
            )

        scored.sort(key=lambda s: (-s.score, s.profile_name))
        best = scored[0] if scored else None

        if best is not None and best.score >= MIN_RECOMMENDATION_SCORE:
            return ResumeRecommendationResponse(
                recommended_profile_id=best.resume_profile_id,
                recommended_profile_name=best.profile_name,
                recommended_specialization=best.specialization,
                job_specializations=job_specializations,
                scores=scored,
                reasons=best.reasons,
            )

        return ResumeRecommendationResponse(
            job_specializations=job_specializations,
            scores=scored,
            reasons=[
                "No confident match: the vacancy could not be tied to any resume profile"
            ],
        )

    def _score_profile(
        self,
        profile: ResumeProfile,
        job_specializations: list[str],
        title: str,
        description: str,
    ) -> tuple[float, list[str]]:
        """Score one profile against the vacancy; returns (score, reasons)."""
        score = 0.0
        reasons: list[str] = []

        # 1) Specialization match — the strongest signal (task spec #16)
        if profile.specialization in job_specializations:
            score += WEIGHT_SPECIALIZATION
            reasons.append(f"vacancy specialization: {profile.specialization}")

        # 2) Specialization keywords (title hits weigh more than body hits)
        keywords = [kw.lower() for kw in (profile.specialization_keywords or []) if kw]
        title_hits = [kw for kw in keywords if _contains_term(title, kw)]
        body_hits = [
            kw
            for kw in keywords
            if kw not in title_hits and _contains_term(description, kw)
        ]
        keyword_score = min(
            len(title_hits) * 3 * WEIGHT_KEYWORD + len(body_hits) * WEIGHT_KEYWORD,
            WEIGHT_KEYWORD_CAP,
        )
        if keyword_score:
            score += keyword_score
            if title_hits:
                reasons.append(f"title keywords: {', '.join(title_hits[:3])}")
            if body_hits:
                reasons.append(f"description keywords: {', '.join(body_hits[:3])}")

        # 3) Selected master skills found in the vacancy (taxonomy-aware)
        matched_skills = [
            skill
            for skill in (profile.selected_skills or [])
            if any(
                _contains_term(title, variant) or _contains_term(description, variant)
                for variant in skill_variants(skill)
            )
        ]
        skill_score = min(len(matched_skills) * WEIGHT_SKILL, WEIGHT_SKILL_CAP)
        if skill_score:
            score += skill_score
            reasons.append(f"matched skills: {', '.join(matched_skills[:5])}")

        return score, reasons
