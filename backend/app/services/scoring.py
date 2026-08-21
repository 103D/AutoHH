"""Deterministic scoring engine for job-candidate matching."""

import re
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.models.candidate import CandidateProfile
from app.models.job import Job


@dataclass
class ScoreBreakdown:
    """Individual score components."""
    technical: float = 0.0          # 0-100: skills/technologies match
    experience: float = 0.0         # 0-100: years/seniority match
    location: float = 0.0           # 0-100: location/remote match
    salary: float = 0.0             # 0-100: salary expectations match
    work_format: float = 0.0        # 0-100: remote/hybrid/office match
    education: float = 0.0          # 0-100: education match
    language: float = 0.0           # 0-100: language match

    def to_dict(self) -> dict[str, float]:
        return {
            "technical": round(self.technical, 1),
            "experience": round(self.experience, 1),
            "location": round(self.location, 1),
            "salary": round(self.salary, 1),
            "work_format": round(self.work_format, 1),
            "education": round(self.education, 1),
            "language": round(self.language, 1),
        }


class ScoringEngine:
    """Calculate deterministic match scores between jobs and candidates."""

    # Words that are too generic to be considered a strong technical match on their own
    STOPWORDS = {"data", "business", "analyst", "experience", "knowledge", "skills", "professional"}

    def __init__(self):
        # Weights normalized to sum to 1.0 for deterministic portion
        self.weights = {
            "technical": 0.30,
            "experience": 0.20,
            "location": 0.10,
            "salary": 0.10,
            "work_format": 0.10,
            "education": 0.10,
            "language": 0.10,
        }

    def _tokenize_text(self, text: str) -> set[str]:
        """Tokenize text into words for skill matching."""
        tokens = re.findall(r'[a-zA-Z0-9+.#-]+', text.lower())
        return set(tokens)

    def _normalize_skills(self, value: Any) -> set[str]:
        """Normalize skills/technologies from list or dict to a set of lowercase strings."""
        if value is None:
            return set()

        if isinstance(value, dict):
            items = value.keys()
        elif isinstance(value, list | tuple | set):
            items = value
        else:
            return set()

        return {str(item).lower().strip() for item in items if item}

    def calculate_technical_score(self, candidate: CandidateProfile, job: Job) -> float:
        """Score based on skills and technologies overlap."""
        candidate_skills = self._normalize_skills(candidate.skills)
        candidate_techs = self._normalize_skills(candidate.technologies)
        candidate_all = candidate_skills | candidate_techs

        if not candidate_all:
            return 50.0  # Neutral if no skills specified

        job_text = f"{job.title} {job.description}"
        job_tokens = self._tokenize_text(job_text)

        matches = 0
        for skill in candidate_all:
            if skill in self.STOPWORDS and len(skill) < 4:
                continue

            skill_tokens = self._tokenize_text(skill)
            if skill_tokens & job_tokens:
                matches += 1

        coverage = matches / len(candidate_all) if candidate_all else 0

        if coverage >= 0.7:
            return 95.0
        elif coverage >= 0.5:
            return 80.0
        elif coverage >= 0.3:
            return 65.0
        elif coverage >= 0.15:
            return 45.0
        else:
            return 25.0

    def calculate_experience_score(self, candidate: CandidateProfile, job: Job) -> float:
        """Score based on experience years match."""
        candidate_years = candidate.experience_years

        if candidate_years is None:
            return 50.0

        job_text = f"{job.title} {job.description}".lower()
        patterns = [
            r"(\d+)\s*\+?\s*years?\s*(?:of\s+)?(?:experience|exp)",
            r"(\d+)\s*\+?\s*years?\s*(?:of\s+)?(?:work|professional)",
            r"minimum\s*(\d+)\s*years?",
            r"at least\s*(\d+)\s*years?",
            r"(\d+)\+\s*years?",
        ]

        required_years = None
        for pattern in patterns:
            match = re.search(pattern, job_text)
            if match:
                required_years = int(match.group(1))
                break

        if required_years is None:
            if any(kw in job.title.lower() for kw in ["senior", "lead", "principal", "staff", "architect"]):
                required_years = 5
            elif any(kw in job.title.lower() for kw in ["middle", "mid"]):
                required_years = 3
            elif any(kw in job.title.lower() for kw in ["junior", "entry", "trainee", "intern"]):
                required_years = 1

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
        else:
            return 25.0

    def _get_candidate_work_formats(self, candidate: CandidateProfile) -> list[str]:
        if not candidate.work_formats:
            return []
        return [fmt.lower() for fmt in candidate.work_formats if fmt]

    def _get_candidate_relocation(self, candidate: CandidateProfile) -> bool:
        return candidate.relocation_possible

    def calculate_location_score(self, candidate: CandidateProfile, job: Job) -> float:
        if not candidate.location and not job.location:
            return 50.0

        candidate_loc = (candidate.location or "").lower()
        job_loc = (job.location or "").lower()

        cand_formats = self._get_candidate_work_formats(candidate)
        cand_relocation = self._get_candidate_relocation(candidate)

        if job.work_format and job.work_format.lower() == "remote":
            if cand_relocation or "remote" in cand_formats:
                return 100.0
            return 80.0

        if job.work_format and job.work_format.lower() == "hybrid":
            if "hybrid" in cand_formats or "office" in cand_formats:
                return 90.0
            if "remote" in cand_formats:
                return 60.0
            if cand_relocation:
                return 70.0
            return 50.0

        if not job.location:
            return 50.0

        if candidate_loc and job_loc:
            if candidate_loc in job_loc or job_loc in candidate_loc:
                return 95.0
            kz_cities = {"almaty", "astana", "nur-sultan", "shymkent", "aktau", "atyrau", "karaganda"}
            if candidate_loc in kz_cities and job_loc in kz_cities:
                if candidate_loc == job_loc:
                    return 95.0
                if not cand_relocation:
                    return 30.0
                return 60.0

        if cand_relocation:
            return 75.0

        return 20.0

    def calculate_salary_score(self, candidate: CandidateProfile, job: Job) -> float:
        if not candidate.desired_salary_min and not candidate.desired_salary_max:
            return 50.0

        if not job.salary_min and not job.salary_max:
            return 50.0

        candidate_min = candidate.desired_salary_min or 0
        candidate_max = candidate.desired_salary_max or float('inf')
        job_min = job.salary_min or 0
        job_max = job.salary_max or float('inf')

        if job_max >= candidate_min and job_min <= candidate_max:
            overlap_min = max(job_min, candidate_min)
            overlap_max = min(job_max, candidate_max)

            candidate_range = candidate_max - candidate_min if candidate_max != float('inf') else 1
            overlap_range = overlap_max - overlap_min

            if candidate_range > 0:
                coverage = overlap_range / candidate_range
                if coverage >= 0.8:
                    return 95.0
                elif coverage >= 0.5:
                    return 80.0
                elif coverage >= 0.2:
                    return 60.0
                return 40.0
            return 70.0
        else:
            if job_min > candidate_max:
                return 95.0
            else:
                gap = candidate_min - job_max
                gap_pct = gap / candidate_min if candidate_min > 0 else 1
                if gap_pct <= 0.1:
                    return 60.0
                elif gap_pct <= 0.25:
                    return 40.0
                else:
                    return 20.0

    def calculate_work_format_score(self, candidate: CandidateProfile, job: Job) -> float:
        cand_formats = self._get_candidate_work_formats(candidate)

        if not cand_formats or not job.work_format:
            return 50.0

        job_fmt = job.work_format.lower()

        if job_fmt in cand_formats:
            return 100.0

        if "remote" in cand_formats and job_fmt == "hybrid":
            return 70.0

        if "hybrid" in cand_formats and job_fmt == "remote":
            return 85.0

        if "office" in cand_formats and job_fmt == "hybrid":
            return 75.0

        if "hybrid" in cand_formats and job_fmt == "office":
            return 60.0

        if "remote" in cand_formats and job_fmt == "office":
            return 20.0

        if "office" in cand_formats and job_fmt == "remote":
            return 40.0

        return 50.0

    def calculate_education_score(self, candidate: CandidateProfile, job: Job) -> float:
        if not candidate.education:
            return 50.0

        job_text = f"{job.title} {job.description}".lower()
        degree_keywords = ["bachelor", "master", "phd", "degree", "diploma", "higher education"]
        requires_degree = any(kw in job_text for kw in degree_keywords)

        if not requires_degree:
            return 70.0

        return 85.0

    def calculate_language_score(self, candidate: CandidateProfile, job: Job) -> float:
        candidate_langs = self._normalize_skills(candidate.languages)

        if not candidate_langs:
            return 50.0

        job_text = f"{job.title} {job.description}".lower()
        lang_keywords = {
            "english": ["english", "en ", "b2", "c1", "c2", "fluent english"],
            "russian": ["russian", "ru ", "русский"],
            "kazakh": ["kazakh", "kk ", "казахский", "қазақ"]
        }

        required_langs = []
        for lang, keywords in lang_keywords.items():
            if any(kw in job_text for kw in keywords):
                required_langs.append(lang)

        if not required_langs:
            return 70.0

        matches = sum(1 for lang in required_langs if lang in candidate_langs)

        if matches == len(required_langs):
            return 95.0
        elif matches > 0:
            return 70.0
        else:
            return 30.0

    def calculate(self, candidate: CandidateProfile, job: Job) -> tuple[float, ScoreBreakdown]:
        breakdown = ScoreBreakdown()

        breakdown.technical = self.calculate_technical_score(candidate, job)
        breakdown.experience = self.calculate_experience_score(candidate, job)
        breakdown.location = self.calculate_location_score(candidate, job)
        breakdown.salary = self.calculate_salary_score(candidate, job)
        breakdown.work_format = self.calculate_work_format_score(candidate, job)
        breakdown.education = self.calculate_education_score(candidate, job)
        breakdown.language = self.calculate_language_score(candidate, job)

        final_score = (
            breakdown.technical * self.weights["technical"] +
            breakdown.experience * self.weights["experience"] +
            breakdown.location * self.weights["location"] +
            breakdown.salary * self.weights["salary"] +
            breakdown.work_format * self.weights["work_format"] +
            breakdown.education * self.weights["education"] +
            breakdown.language * self.weights["language"]
        )

        return round(final_score, 1), breakdown

    def get_recommendation(self, score: float) -> str:
        if score >= settings.threshold_high_priority:
            return "HIGH_PRIORITY"
        elif score >= settings.threshold_apply:
            return "APPLY"
        elif score >= settings.threshold_review:
            return "REVIEW"
        else:
            return "IGNORE"
