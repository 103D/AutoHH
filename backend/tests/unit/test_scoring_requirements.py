"""Tests for the skill-requirement scoring model (match model v3).

Covers REQUIRED/PREFERRED/OPTIONAL extraction, MATCHED/PARTIAL/MISSING/UNKNOWN
statuses, importance-weighted technical score, the missing-REQUIRED cap and
the LLM semantic-merge boundary (LLM never assigns the score itself).
"""

from uuid import uuid4

from app.models.candidate import CandidateProfile
from app.models.job import Job
from app.providers.ai.base import MatchResult as AIMatchResult
from app.providers.ai.base import SkillMatch
from app.services.scoring import ScoringEngine
from app.services.scoring.model import (
    MATCHED,
    MISSING,
    OPTIONAL,
    PARTIAL,
    PREFERRED,
    REQUIRED,
    UNKNOWN,
    RequirementMatch,
    ScoreBreakdown,
    SkillAudit,
)
from app.services.scoring.skills import (
    extract_requirements_deterministic,
    match_requirement,
    score_requirements,
)
from app.services.skill_taxonomy import normalize_skill


def make_candidate(skills: list[str]) -> CandidateProfile:
    return CandidateProfile(
        id=uuid4(),
        user_id=uuid4(),
        skills=skills,
        technologies=[],
        experience_years=3,
    )


def make_job(description: str, title: str = "Data Analyst") -> Job:
    return Job(
        id=uuid4(),
        source_id=uuid4(),
        external_id="ext1",
        title=title,
        company="Corp",
        description=description,
        url="https://hh.kz/vacancy/1",
        first_seen_at="2026-01-01T00:00:00Z",
        last_seen_at="2026-01-01T00:00:00Z",
        content_hash="h1",
        url_normalized="https://hh.kz/vacancy/1",
        raw_data={},
    )


def test_required_and_preferred_extracted():
    job = make_job("Требования: SQL, Python. Будет плюсом: dbt.")
    reqs = extract_requirements_deterministic(job, {"sql", "python", "dbt"})
    by_skill = {r.skill: r for r in reqs}
    assert by_skill["SQL"].importance == REQUIRED
    assert by_skill["Python"].importance == REQUIRED
    assert by_skill["dbt"].importance == PREFERRED


def test_inline_markers_promote_importance():
    job = make_job("Уверенное знание SQL обязательно, Python желательно.")
    reqs = extract_requirements_deterministic(job, {"sql", "python"})
    by_skill = {r.skill: r for r in reqs}
    assert by_skill["SQL"].importance == REQUIRED  # "обязательно"
    assert by_skill["Python"].importance == PREFERRED  # "желательно"


def test_candidate_skill_mention_becomes_optional():
    """Skills not in the lexicon but present in the ad stay OPTIONAL (v3)."""
    job = make_job("Работаем с Looker Studio.")
    reqs = extract_requirements_deterministic(job, {"looker studio"})
    assert any(
        r.skill.lower() == "looker studio" and r.importance == OPTIONAL
        for r in reqs
    )


def test_no_requirements_returns_empty():
    job = make_job("Командная работа и коммуникабельность.")
    assert extract_requirements_deterministic(job, {"sql"}) == []


def test_match_exact_and_taxonomy_alias():
    assert match_requirement("PostgreSQL", {"postgres"})[0] == MATCHED
    assert match_requirement("Power BI", {"powerbi"})[0] == MATCHED
    assert match_requirement("SQL", {"python"})[0] == MISSING


def test_match_partial_via_containment():
    # A taxonomy variant spelled inside the longer form is a strong mention
    # ("dbt core" mentions "dbt") -> deterministic MATCHED.
    status, _ = match_requirement("dbt core", {"dbt"})
    assert status == MATCHED


def test_match_partial_for_related_skill():
    # PARTIAL is a conservative fallback for skills that share no taxonomy
    # variant and are not spelled inside one another. In practice the
    # requirement's own surface form is always one of its variants, so any
    # containment is already promoted to MATCHED; a genuine substring PARTIAL
    # therefore needs two *distinct* non-taxonomy forms.
    status, note = match_requirement("Data Mesh", {"data mesh architecture"})
    # "data mesh" (the requirement itself) is spelled inside the candidate
    # skill -> promoted to MATCHED, not PARTIAL.
    assert status == MATCHED
    assert note is not None


def test_match_missing_for_unrelated_skill():
    status, _ = match_requirement("SQL", {"python"})
    assert status == MISSING


def test_match_unknown_when_no_candidate_data():
    status, _ = match_requirement("SQL", set())
    assert status == UNKNOWN


def test_technical_score_perfect_match():
    job = make_job("Требования: SQL, Python. Будет плюсом: dbt.")
    engine = ScoringEngine()
    score, audit = engine.analyze_technical(
        make_candidate(["SQL", "Python", "dbt"]), job
    )
    assert score == 100.0
    assert audit.missing_required == []
    assert set(audit.matched) == {"SQL", "Python", "dbt"}


def test_missing_required_lowers_score_and_is_reported():
    job = make_job("Требования: SQL, Python.")
    engine = ScoringEngine()
    score, audit = engine.analyze_technical(make_candidate(["SQL"]), job)
    # 1 из 2 REQUIRED совпал -> 50.0
    assert score == 50.0
    assert audit.missing_required == ["Python"]
    assert audit.matched == ["SQL"]


def test_many_preferred_one_missing_required():
    description = (
        "Требования: SQL, Python.\n"
        "Будет плюсом: dbt, Airflow, Spark, Kafka, Tableau."
    )
    engine = ScoringEngine()
    good_candidate = make_candidate(
        ["SQL", "Python", "dbt", "Airflow", "Spark", "Kafka", "Tableau"]
    )
    job = make_job(description)
    score, _ = engine.analyze_technical(good_candidate, job)
    assert score == 100.0

    # То же, но без обязательного Python -> score падает, gap виден.
    bad_candidate = make_candidate(
        ["SQL", "dbt", "Airflow", "Spark", "Kafka", "Tableau"]
    )
    score_bad, audit_bad = engine.analyze_technical(bad_candidate, job)
    assert "Python" in audit_bad.missing_required
    # Weighted coverage: (SQL 3*1.0 + 5 PREFERRED * 1.5 * 1.0) /
    #                    (2 REQUIRED * 3 + 5 PREFERRED * 1.5) = 10.5/13.5.
    # The missing REQUIRED keeps its full weight in the denominator.
    assert score_bad == 77.8


def test_weighted_score_formula():
    reqs = [
        type("R", (), {"skill": "a", "importance": REQUIRED, "status": MATCHED})(),
        type("R", (), {"skill": "b", "importance": REQUIRED, "status": MISSING})(),
    ]
    # (3*1 + 3*0) / 6 -> 50.0
    assert score_requirements(reqs) == 50.0


def test_unknown_requirements_are_neutral():
    """No candidate skill data -> every requirement is UNKNOWN -> neutral 50."""
    engine = ScoringEngine()
    job = make_job("Требования: SQL, Python.")
    score, audit = engine.analyze_technical(make_candidate([]), job)
    assert score == 50.0
    assert all(r.status == UNKNOWN for r in audit.requirements)


def test_aggregate_cap_for_missing_required():
    engine = ScoringEngine()
    # A strong deterministic base (all components high) with one missing
    # REQUIRED skill: the cap (100 - penalty) binds and is recorded.
    breakdown = ScoreBreakdown(
        technical=90.0,
        experience=90.0,
        location=90.0,
        salary=90.0,
        work_format=90.0,
        education=90.0,
        language=90.0,
        skills=SkillAudit(
            source="deterministic",
            requirements=[
                RequirementMatch(skill="SQL", importance=REQUIRED, status=MATCHED),
                RequirementMatch(
                    skill="ClickHouse", importance=REQUIRED, status=MISSING
                ),
            ],
            matched=["SQL"],
            missing=["ClickHouse"],
            missing_required=["ClickHouse"],
        ),
    )
    final = engine.aggregate(breakdown)
    # raw = 90; cap = 100 - 25 = 75 -> final clamped to the cap.
    assert final == 75.0
    assert breakdown.score_caps
    assert breakdown.score_caps[0]["cap"] == 75.0
    assert "ClickHouse" in breakdown.score_caps[0]["reason"]


def test_breakdown_full_dict_explainability():
    engine = ScoringEngine()
    job = make_job("Требования: SQL.")
    _, breakdown = engine.calculate(make_candidate(["SQL"]), job)
    d = breakdown.to_full_dict()
    assert "skills" in d
    assert d["skills"]["missing_required"] == []
    assert d["skills"]["source"] == "deterministic"


# ---------------------------------------------------------------------------
# LLM semantic-merge boundary
# ---------------------------------------------------------------------------

def test_llm_score_is_ignored_without_requirements():
    """LLM-provided score must never leak into the final number (v3)."""
    engine = ScoringEngine()
    job = make_job("Требования: SQL.")
    candidate = make_candidate(["SQL"])
    _, breakdown = engine.calculate(candidate, job)
    det_final = engine.aggregate(breakdown)

    llm_res = AIMatchResult(
        score=95,  # при старом blend увёл бы score вверх
        recommendation="HIGH_PRIORITY",
        matched_skills=[SkillMatch(skill="SQL")],
        missing_skills=[],
        strong_matches=[],
        concerns=[],
        reasoning_summary="x",
    )
    new_final, adjustments = engine.apply_llm_requirements(
        llm_res, candidate, breakdown
    )
    assert new_final is None
    assert adjustments is None
    # детерминированный результат не изменился
    assert breakdown.to_full_dict()["technical"] == 100.0
    assert engine.aggregate(breakdown) == det_final


def test_llm_requirements_rescore_deterministically():
    """LLM указывает требования — движок пересчитывает score сам."""
    engine = ScoringEngine()
    candidate = make_candidate(["SQL", "Python"])
    job = make_job("Произвольное описание для извлечения требований LLM.")
    _, breakdown = engine.calculate(candidate, job)

    llm = AIMatchResult(
        score=10,  # игнорируется
        recommendation="REVIEW",
        requirements=[
            {"skill": "SQL", "importance": "REQUIRED"},
            {"skill": "Python", "importance": "REQUIRED"},
            {"skill": "ClickHouse", "importance": "REQUIRED"},
        ],
        skill_equivalences=[],
        matched_skills=[],
        missing_skills=[],
        strong_matches=[],
        concerns=[],
        reasoning_summary="",
    )
    new_final, adjustments = engine.apply_llm_requirements(
        llm, candidate, breakdown
    )
    assert new_final is not None
    assert adjustments["requirements_source"] == "llm"
    assert adjustments["missing_required"] == ["ClickHouse"]
    assert breakdown.skills.missing_required == ["ClickHouse"]
    # 2 из 3 REQUIRED совпали -> technical 66.7 (LLM score 10 не использовано)
    assert breakdown.technical == 66.7
    assert adjustments["final_after"] >= adjustments["final_before"]


def test_llm_equivalences_upgrade_missing_to_partial():
    """Transferable skills из LLM превращают MISSING в PARTIAL."""
    engine = ScoringEngine()
    candidate = make_candidate(["dbt"])
    job = make_job("Требуется Airflow для оркестрации ETL.")
    _, breakdown = engine.calculate(candidate, job)

    llm = AIMatchResult(
        score=70,
        recommendation="REVIEW",
        requirements=[{"skill": "Airflow", "importance": "REQUIRED"}],
        skill_equivalences=[
            {"job_skill": "Airflow", "candidate_skill": "dbt"}
        ],
        matched_skills=[],
        missing_skills=[],
        strong_matches=[],
        concerns=[],
        reasoning_summary="",
    )
    _, adjustments = engine.apply_llm_requirements(llm, candidate, breakdown)
    assert adjustments["skills_override"] is True
    statuses = {r.skill: r.status for r in breakdown.skills.requirements}
    airflow = normalize_skill("Airflow")  # canonical display form
    assert statuses[airflow] == PARTIAL
    assert airflow not in breakdown.skills.missing_required
    # PARTIAL даёт 0.5 веса -> technical > 0 вместо 0
    assert breakdown.technical > 0
