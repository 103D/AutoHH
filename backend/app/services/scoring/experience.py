"""Experience score component (match model v3).

Single place for required-experience resolution: the normalized
``job.experience_required`` field first, then the shared deterministic parser
(``app/utils/experience.py``), then a title-based seniority heuristic. The
previous per-file regexes duplicate the parser and were dropped.
"""

from app.models.candidate import CandidateProfile
from app.models.job import Job
from app.utils.experience import extract_required_experience_years

SENIOR_TITLE_WORDS = ("senior", "lead", "principal", "staff", "architect")
MIDDLE_TITLE_WORDS = ("middle", "mid")
JUNIOR_TITLE_WORDS = ("junior", "entry", "trainee", "intern")


def required_years_from_title(title: str | None) -> int | None:
    text = (title or "").lower()
    if any(word in text for word in SENIOR_TITLE_WORDS):
        return 5
    if any(word in text for word in MIDDLE_TITLE_WORDS):
        return 3
    if any(word in text for word in JUNIOR_TITLE_WORDS):
        return 1
    return None


def extract_required_years(job: Job) -> int | None:
    """Required years: normalized field > shared parser > title heuristic."""
    if getattr(job, "experience_required", None) is not None:
        return int(job.experience_required)
    years = extract_required_experience_years(job.description)
    if years is not None:
        return years
    return required_years_from_title(job.title)


def experience_score(candidate: CandidateProfile, job: Job) -> float:
    """0-100: how well the candidate's years match the vacancy requirement."""
    candidate_years = candidate.experience_years
    if candidate_years is None:
        return 50.0

    required_years = extract_required_years(job)
    if required_years is None:
        return 50.0

    diff = candidate_years - required_years
    if diff >= 3:
        return 95.0
    elif diff >= 1:
        return 90.0
    elif diff == 0:
        return 85.0
    elif diff >= -1:
        return 70.0
    elif diff >= -2:
        return 50.0
    return 25.0
