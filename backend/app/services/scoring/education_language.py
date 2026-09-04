"""Education and language score components (match model v3)."""

from app.models.candidate import CandidateProfile
from app.models.job import Job

_DEGREE_KEYWORDS = [
    "bachelor", "master", "phd", "degree", "diploma", "higher education",
]

_LANGUAGE_KEYWORDS = {
    "english": ["english", "en ", "b2", "c1", "c2", "fluent english"],
    "russian": ["russian", "ru ", "русский"],
    "kazakh": ["kazakh", "kk ", "казахский", "қазақ"],
}


def education_score(candidate: CandidateProfile, job: Job) -> float:
    if not candidate.education:
        return 50.0

    job_text = f"{job.title} {job.description}".lower()
    requires_degree = any(kw in job_text for kw in _DEGREE_KEYWORDS)

    if not requires_degree:
        return 70.0

    return 85.0


def language_score(candidate: CandidateProfile, job: Job) -> float:
    candidate_langs: set[str] = set()
    if isinstance(candidate.languages, dict):
        candidate_langs = {str(k).lower() for k in candidate.languages if k}
    elif isinstance(candidate.languages, list | tuple | set):
        candidate_langs = {
            str(lang).lower() for lang in candidate.languages if lang
        }

    if not candidate_langs:
        return 50.0

    job_text = f"{job.title} {job.description}".lower()

    required_langs: list[str] = []
    for lang, keywords in _LANGUAGE_KEYWORDS.items():
        if any(kw in job_text for kw in keywords):
            required_langs.append(lang)

    if not required_langs:
        return 70.0

    matches = sum(1 for lang in required_langs if lang in candidate_langs)

    if matches == len(required_langs):
        return 95.0
    elif matches > 0:
        return 70.0
    return 30.0
