"""Skill requirement extraction and matching (match model v3).

Responsibilities
----------------
- deterministic extraction of REQUIRED / PREFERRED / OPTIONAL requirements
  from a vacancy text;
- matching candidate skills against requirements
  (MATCHED / PARTIAL / MISSING / UNKNOWN);
- the weighted technical score (importance-based requirement coverage);
- re-scoring from LLM-extracted requirements + transferable equivalents;
- the legacy candidate-coverage heuristic used when no requirements can be
  extracted (documented fallback, flagged via ``SkillAudit.source``).

Design notes
------------
The technical score measures *how well the candidate covers the job's
requirements*, not *how many of the candidate's skills appear in the job*
(the old, inverted metric). REQUIRED skills carry a 3x weight vs OPTIONAL;
their absence both lowers the score and is reported separately in
``SkillAudit.missing_required``.
"""

import re

from app.core.config import settings
from app.models.job import Job
from app.services.scoring.model import (
    DEFAULT_IMPORTANCE_WEIGHTS,
    IMPORTANCE_LEVELS,
    MATCHED,
    MISSING,
    OPTIONAL,
    OPTIONAL_WEIGHT,
    PARTIAL,
    PREFERRED,
    REQ_SOURCE_DETERMINISTIC,
    REQ_SOURCE_LLM,
    REQUIRED,
    STATUS_VALUE,
    UNKNOWN,
    RequirementMatch,
    SkillAudit,
)
from app.services.scoring.tokenize import tokenize_text
from app.services.skill_taxonomy import (
    ALIASES_BY_CANONICAL,
    CANONICAL_SKILLS,
    canonical_key,
    normalize_skill,
    skill_variants,
)

# Words too generic to be a strong technical requirement on their own.
SKILL_STOPWORDS = {
    "data", "business", "analyst", "experience", "knowledge", "skills",
    "professional", "analysis", "analytics",
}

# ============================================================================
# Skill lexicon (canonical display name -> lowercase mention forms).
# ============================================================================

# Common skills absent from the taxonomy that still matter for analytics
# vacancies. Added only for extraction; the taxonomy remains the authority
# for aliasing between canonical forms.
EXTRA_LEXICON: dict[str, set[str]] = {
    "dbt": {"dbt", "dbt core", "датабилд"},
    "dbt Cloud": {"dbt cloud"},
    "ETL": {"etl", "etl-процессы", "etl-процесс"},
    "FastAPI": {"fastapi"},
    "Django": {"django"},
    "Flask": {"flask"},
    "React": {"react", "reactjs", "react.js"},
    "Redux": {"redux"},
    "Spring": {"spring", "spring boot", "springboot"},
    "C++": {"c++"},
    "C#": {"c#", "csharp"},
    "Golang": {"golang"},
    "Rust": {"rust"},
    "Scala": {"scala"},
    "HTML": {"html"},
    "CSS": {"css"},
    "REST API": {"rest api", "restful"},
    "GraphQL": {"graphql"},
    "Redis": {"redis"},
    "MongoDB": {"mongodb", "mongo"},
    "RabbitMQ": {"rabbitmq"},
    "Nginx": {"nginx"},
    "Linux": {"linux"},
    "AWS": {"aws", "amazon web services", "amazon aws"},
    "GCP": {"gcp", "google cloud platform", "google cloud"},
    "Azure": {"azure", "microsoft azure"},
    "Terraform": {"terraform"},
    "Jenkins": {"jenkins"},
    "GitHub Actions": {"github actions"},
    "GitLab CI": {"gitlab ci", "gitlabci"},
    "Statistics": {"statistics", "статистика", "статистических", "статистическ"},
    "A/B Testing": {"a/b testing", "a/b test", "ab testing", "ab test", "a/b-тест", "ab-тест", "а/б-тест", "аб-тест", "сплит-тест"},
    "Unit Economics": {"unit economics", "unit-экономика", "юнит-экономика"},
    "Funnel Analysis": {"funnel analysis", "analysis of funnels", "воронк"},
    "Cohort Analysis": {"cohort analysis", "cohorts", "когорт"},
    "Retention": {"retention", "churn", "отток"},
    "Databricks": {"databricks"},
    "Snowflake": {"snowflake"},
    "Redshift": {"redshift"},
    "BigQuery": {"bigquery"},
    "GoodData": {"gooddata"},
}


def _build_lexicon() -> dict[str, set[str]]:
    """Canonical display name -> lowercase mention forms for extraction."""
    lexicon: dict[str, set[str]] = {}
    for key, display in CANONICAL_SKILLS.items():
        forms = {key, display.lower(), *ALIASES_BY_CANONICAL.get(key, [])}
        lexicon[display] = forms
    existing = {canonical_key(s) for s in lexicon}
    for display, forms in EXTRA_LEXICON.items():
        if canonical_key(display) in existing:
            continue  # taxonomy already covers this skill
        lexicon[display] = {f.strip().lower() for f in forms if f.strip()}
        existing.add(canonical_key(display))
    return lexicon


SKILL_LEXICON: dict[str, set[str]] = _build_lexicon()

# ============================================================================
# Requirement importance from context (deterministic).
# ============================================================================

_SECTION_REQUIRED = re.compile(
    r"(требовани|обязательн|required|must-have|must have|hard skills|"
    r"essential|необходим|критерии|you will need|you'?ll need|"
    r"we are looking for|мы ищем|что нужно|ожидаем от кандидата|"
    r"ключевые навыки)",
    re.IGNORECASE,
)
_SECTION_PREFERRED = re.compile(
    r"(будет плюсом|плюсом будет|преимуществ|preferred|nice-?to-?have|"
    r"good-?to-?have|a plus|приветству|желательн|бонус|"
    r"было бы здорово)",
    re.IGNORECASE,
)
_REQUIRED_MARKERS = re.compile(
    r"(required|must|must-have|hard requirement|обязательн|требуется|"
    r"требуются|необходим|essential|критическ|strict(ly)?)",
    re.IGNORECASE,
)
_PREFERRED_MARKERS = re.compile(
    r"(preferred|a plus|nice-?to-?have|good-?to-?have|будет плюсом|"
    r"плюсом будет|желательн|приветствуется|преимуществ)",
    re.IGNORECASE,
)

_TITLE_LINE_BREAK = True


# A word that introduces a new requirement/section. A following inline marker
# ("обязательно" / "желательно") is attributed to the skill that came right
# before the connector, not to the whole line.
_CONNECTORS = re.compile(
    r"^("
    r"и|а|или|and|or|with|для|на|во|в|по|знание|опыт|уверенное|хорошее|"
    r"глубокое|понимание|владение|умение|знакомство|работа|работы|навык|навыки|"
    r"знания|технологии|инструменты|стек|плюс|также|прочее|the|a|an|of"
    r")\b[\s,.:;!?()]*",
    re.IGNORECASE,
)


def _importance_of_line(line: str, is_title: bool = False) -> str:
    """Classify a whole line (fallback when no finer context is found)."""
    if _REQUIRED_MARKERS.search(line):
        return REQUIRED
    if _PREFERRED_MARKERS.search(line):
        return PREFERRED
    if _SECTION_REQUIRED.search(line):
        return REQUIRED
    if _SECTION_PREFERRED.search(line):
        return PREFERRED
    if is_title:
        return REQUIRED
    return OPTIONAL


def _mentioned(line: str, variant: str) -> bool:
    """Word-boundary mention check (`sql` must not match inside `mysql`)."""
    if not variant:
        return False
    if " " in variant:
        return variant in line
    return (
        re.search(rf"(?<![a-zа-я0-9]){re.escape(variant)}(?![a-zа-я0-9])", line)
        is not None
    )


def _classify_line(line: str, is_title: bool = False) -> list[tuple[str, str]]:
    """Classify a line into ``(clause_text, importance)`` pairs.

    Vacancy text rarely puts one skill per line — section headers and inline
    markers share a single line ("Требования: SQL, Python. Будет плюсом: dbt.",
    "SQL обязательно, Python желательно."). So we split the line into clauses
    and track a running *current* importance that:

    - is set by a section header ("Требования:", "Будет плюсом:") and applies
      to the skills listed after it;
    - is set by an inline marker, attributed to the clause that immediately
      precedes it ("SQL обязательно", "Python желательно");
    - carries across bare list separators (", ", " и ") inside the section;
    - resets at sentence / section boundaries.

    Every clause keeps the importance that was active *when the clause
    started*; an inline marker then retroactively upgrades that same clause.
    """
    if _REQUIRED_MARKERS.search(line) and not (
        _SECTION_PREFERRED.search(line) or _PREFERRED_MARKERS.search(line)
    ):
        line_level = REQUIRED
    elif _PREFERRED_MARKERS.search(line) or _SECTION_PREFERRED.search(line):
        line_level = PREFERRED
    elif _SECTION_REQUIRED.search(line):
        line_level = REQUIRED
    else:
        line_level = REQUIRED if is_title else OPTIONAL

    result: list[tuple[str, str]] = []
    current = line_level
    for segment in re.split(r"[.\n\r;]+", line):
        seg = segment.strip()
        if not seg:
            continue
        seg_req = bool(_SECTION_REQUIRED.search(seg))
        seg_pref = bool(_SECTION_PREFERRED.search(seg))
        if seg_req and not seg_pref:
            current = REQUIRED
        elif seg_pref:
            current = PREFERRED

        for clause in re.split(r"[,]+", seg):
            c = clause.strip()
            if not c:
                continue
            result.append((c, current))
            # An inline marker applies to the clause that precedes it; the
            # NEXT clause is a fresh item and must not inherit the marker.
            if _REQUIRED_MARKERS.search(c):
                result[-1] = (c, REQUIRED)
                current = REQUIRED
            elif _PREFERRED_MARKERS.search(c):
                result[-1] = (c, PREFERRED)
                current = PREFERRED
    return result


def _ranks(importance: str) -> int:
    return {REQUIRED: 3, PREFERRED: 2, OPTIONAL: 1}.get(importance, 0)


def extract_requirements_deterministic(
    job: Job,
    candidate_skills: set[str],
) -> list[RequirementMatch]:
    """Extract REQUIRED/PREFERRED/OPTIONAL requirements from a vacancy.

    Deterministic only (no LLM): scans the text for known lexicon skills
    and candidate-skill mentions, then classifies importance from section
    headers and inline markers. Returns [] when nothing usable is found —
    the engine then falls back to the legacy candidate-coverage heuristic.
    """
    title = (job.title or "").lower()
    description = (job.description or "").lower()

    # skill display -> best (highest-importance) context it appeared in.
    best_importance: dict[str, str] = {}

    def record(display: str, importance: str) -> None:
        current = best_importance.get(display)
        if _ranks(importance) > _ranks(current or OPTIONAL):
            best_importance[display] = importance

    # A skill mentioned only in the title (with no stronger context in the
    # description) is a soft signal: the role itself, not an explicit demand.
    for display, forms in SKILL_LEXICON.items():
        for form in forms:
            if _mentioned(title, form):
                record(display, OPTIONAL)
                break

    # Scan every description line once. Each line is classified into
    # (clause, importance) pairs; a skill takes the importance of the clause
    # it is mentioned in (section header or inline marker), so "Требования:"
    # and "Будет плюсом:" apply to their own skills even on a shared line.
    lines = [ln.strip() for ln in re.split(r"[\n\r;]+", description) if ln.strip()]
    for line in lines:
        classified = _classify_line(line)
        for display, forms in SKILL_LEXICON.items():
            if best_importance.get(display) == REQUIRED:
                continue  # cannot be upgraded further
            for clause, importance in classified:
                if any(_mentioned(clause, form) for form in forms):
                    record(display, importance)
                    break

    requirements = [
        RequirementMatch(
            skill=normalize_skill(display) or display,
            importance=importance,
            source=REQ_SOURCE_DETERMINISTIC,
        )
        for display, importance in best_importance.items()
    ]

    # Supplement: candidate skills that are mentioned in the vacancy but are
    # not in the lexicon become OPTIONAL requirements. This keeps the
    # information that "the candidate's stack is present in the ad" in the
    # requirement frame instead of being silently dropped.
    return _supplement_candidate_skills(
        requirements, title, description, candidate_skills
    )


def _supplement_candidate_skills(
    requirements: list[RequirementMatch],
    title: str,
    description: str,
    candidate_skills: set[str],
) -> list[RequirementMatch]:
    existing = {canonical_key(r.skill) for r in requirements}
    job_text = f"{title} {description}"
    job_tokens = tokenize_text(job_text)
    for skill in sorted(candidate_skills):
        key = canonical_key(skill)
        if key in existing or not key:
            continue
        if skill_variants(skill) & job_tokens or tokenize_text(skill) & job_tokens:
            requirements.append(
                RequirementMatch(
                    skill=normalize_skill(skill) or skill,
                    importance=OPTIONAL,
                    source=REQ_SOURCE_DETERMINISTIC,
                    note="candidate skill mentioned in the vacancy",
                )
            )
            existing.add(key)
    return requirements


# ============================================================================
# Matching candidate skills against requirements.
# ============================================================================

def match_requirement(
    req_skill: str, candidate_skills: set[str]
) -> tuple[str, str | None]:
    """Return ``(status, note)`` for one requirement against the candidate."""
    if not candidate_skills:
        return UNKNOWN, "candidate has no skill data"

    # Alias / canonical equivalence via the taxonomy ("postgres" -> PostgreSQL).
    req_variants = skill_variants(req_skill)
    for skill in candidate_skills:
        if skill_variants(skill) & req_variants:
            return MATCHED, None

    # Mention equivalence: a taxonomy variant spelled inside the longer form
    # ("dbt core" mentions "dbt"). Deterministic and stronger than a vague
    # substring PARTIAL.
    for skill in candidate_skills:
        s = skill.strip().lower()
        if len(s) < 3:
            continue
        for variant in req_variants:
            v = variant.strip().lower()
            if len(v) >= 3 and v != s and (v in s or s in v):
                return MATCHED, f"mentioned variant: {variant}"

    req_tokens = tokenize_text(req_skill)
    for skill in candidate_skills:
        skill_tokens = tokenize_text(skill)
        if req_tokens and skill_tokens and req_tokens <= skill_tokens:
            return MATCHED, None

    # Conservative PARTIAL: one side is contained in the other (min length 3).
    req_norm = req_skill.strip().lower()
    for skill in candidate_skills:
        s = skill.strip().lower()
        if len(s) >= 3 and len(req_norm) >= 3 and (s in req_norm or req_norm in s):
            return PARTIAL, f"candidate has related skill: {skill}"

    return MISSING, None


def audit_from_requirements(
    requirements: list[RequirementMatch],
    source: str = REQ_SOURCE_DETERMINISTIC,
) -> SkillAudit:
    """Build the explainability audit and derive matched/missing lists."""
    audit = SkillAudit(source=source, requirements=list(requirements))
    for req in audit.requirements:
        if req.status == MATCHED:
            audit.matched.append(req.skill)
        elif req.status == MISSING:
            audit.missing.append(req.skill)
        elif req.status == UNKNOWN:
            audit.unknown.append(req.skill)
        if req.importance == REQUIRED and req.status == MISSING:
            audit.missing_required.append(req.skill)
    return audit


def score_requirements(
    requirements: list[RequirementMatch],
    weights: dict[str, float] | None = None,
) -> float:
    """Weighted requirement-coverage technical score (0-100).

    ``score = 100 * Σ(w_i * value_i) / Σ(w_i)`` over the requirements that
    can be judged; UNKNOWN requirements are excluded from both sums (no
    candidate data), never from the displayed list.
    """
    w = {**DEFAULT_IMPORTANCE_WEIGHTS, **(weights or {})}
    judged = [r for r in requirements if r.status != UNKNOWN]
    if not judged:
        return 50.0
    total = sum(w.get(r.importance, OPTIONAL_WEIGHT) for r in judged)
    if total <= 0:
        return 50.0
    weighted = sum(
        w.get(r.importance, OPTIONAL_WEIGHT) * STATUS_VALUE[r.status]
        for r in judged
    )
    return round(100.0 * weighted / total, 1)


# ============================================================================
# Legacy heuristic fallback (candidate-coverage).
# ============================================================================

def heuristic_technical_score(candidate_skills: set[str], job: Job) -> float:
    """Legacy score: how much of the *candidate's* stack appears in the job.

    Flagged in the breakdown as ``skills.source == "heuristic"``. Used only
    when no requirements can be extracted from the vacancy text at all.
    """
    if not candidate_skills:
        return 50.0
    job_tokens = tokenize_text(f"{job.title} {job.description}")
    matches = 0
    for skill in candidate_skills:
        if skill in SKILL_STOPWORDS and len(skill) < 4:
            continue
        variants = skill_variants(skill)
        if variants & job_tokens or tokenize_text(skill) & job_tokens:
            matches += 1

    coverage = matches / len(candidate_skills)
    if coverage >= 0.7:
        return 95.0
    elif coverage >= 0.5:
        return 80.0
    elif coverage >= 0.3:
        return 65.0
    elif coverage >= 0.15:
        return 45.0
    return 25.0


def analyze_technical(
    candidate_skills: set[str], job: Job
) -> tuple[float, SkillAudit]:
    """Full deterministic technical pipeline: extract -> match -> score.

    Returns ``(score, audit)``. The audit explains *why* the score is what it
    is (per-skill statuses, missing required skills, source of the list).
    """
    if not candidate_skills:
        requirements = extract_requirements_deterministic(job, set())
        if requirements:
            for req in requirements:
                req.status = UNKNOWN
                req.note = req.note or "candidate has no skill data"
            return 50.0, audit_from_requirements(requirements)
        return 50.0, SkillAudit(source="heuristic")

    requirements = extract_requirements_deterministic(job, candidate_skills)
    if not requirements:
        return heuristic_technical_score(candidate_skills, job), SkillAudit(
            source="heuristic"
        )

    for req in requirements:
        req.status, note = match_requirement(req.skill, candidate_skills)
        req.note = note or req.note
    audit = audit_from_requirements(requirements)
    return score_requirements(requirements), audit


def find_candidate_matches(
    candidate_skills: set[str], job: Job
) -> tuple[list[str], list[str]]:
    """Candidate skills found / not found in the vacancy text (display lists).

    This is intentionally *not* the scoring source anymore — it feeds the
    ``matched_skills`` / ``missing_skills`` response fields, whose semantics
    the frontend already depends on ("which of my stack does this job mention").
    """
    job_tokens = tokenize_text(f"{job.title} {job.description}")
    matched: list[str] = []
    missing: list[str] = []
    for skill in sorted(candidate_skills):
        if skill in SKILL_STOPWORDS and len(skill) < 4:
            continue
        if skill_variants(skill) & job_tokens or tokenize_text(skill) & job_tokens:
            matched.append(skill)
        else:
            missing.append(skill)
    return matched, missing


# ============================================================================
# LLM-assisted re-scoring (semantic interpretation boundary).
# ============================================================================

def re_score_from_llm(
    requirements: list[RequirementMatch],
    equivalences: list[dict | object] | None,
    candidate_skills: set[str],
) -> SkillAudit:
    """Build a SkillAudit from LLM-extracted requirements.

    The LLM owns *semantic interpretation* (what the vacancy really asks for,
    normalized names, equivalents, transferable skills); the mechanical
    match statuses and the numeric score stay deterministic here.
    """
    reqs: list[RequirementMatch] = []
    for item in requirements:
        if isinstance(item, dict):
            skill_raw = item.get("skill")
            importance = item.get("importance")
            note = item.get("note")
        else:
            skill_raw = getattr(item, "skill", None)
            importance = getattr(item, "importance", None)
            note = getattr(item, "note", None)
        skill = normalize_skill(str(skill_raw).strip() if skill_raw else "")
        if not skill:
            continue
        if importance not in IMPORTANCE_LEVELS:
            importance = OPTIONAL
        req = RequirementMatch(
            skill=skill,
            importance=importance,
            source=REQ_SOURCE_LLM,
            note=note,
        )
        req.status, match_note = match_requirement(skill, candidate_skills)
        req.note = match_note or note
        reqs.append(req)

    for eq in equivalences or []:
        if isinstance(eq, dict):
            job_skill_raw = eq.get("job_skill")
            cand_skill_raw = eq.get("candidate_skill")
        else:
            job_skill_raw = getattr(eq, "job_skill", None)
            cand_skill_raw = getattr(eq, "candidate_skill", None)
        job_skill = normalize_skill(
            str(job_skill_raw).strip() if job_skill_raw else ""
        )
        cand_skill = str(cand_skill_raw or "").strip().lower()
        if not job_skill or not cand_skill or cand_skill not in candidate_skills:
            continue
        for req in reqs:
            if (
                canonical_key(req.skill) == canonical_key(job_skill)
                and req.status in (MISSING, PARTIAL)
            ):
                req.status = PARTIAL
                req.note = f"transferable skill: {cand_skill_raw}"
    return audit_from_requirements(reqs, source=REQ_SOURCE_LLM)


def choose_importance_weights() -> dict[str, float]:
    """Importance weights, overridable via settings (kept explicit)."""
    return {
        REQUIRED: settings.score_required_skill_weight,
        PREFERRED: settings.score_preferred_skill_weight,
        OPTIONAL: settings.score_optional_skill_weight,
    }
