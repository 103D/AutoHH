"""Salary score component (match model v3)."""

from app.models.candidate import CandidateProfile
from app.models.job import Job


def salary_score(candidate: CandidateProfile, job: Job) -> float:
    if not candidate.desired_salary_min and not candidate.desired_salary_max:
        return 50.0

    if not job.salary_min and not job.salary_max:
        return 50.0

    candidate_min = candidate.desired_salary_min or 0
    candidate_max = candidate.desired_salary_max or float("inf")
    job_min = job.salary_min or 0
    job_max = job.salary_max or float("inf")

    if job_max >= candidate_min and job_min <= candidate_max:
        overlap_min = max(job_min, candidate_min)
        overlap_max = min(job_max, candidate_max)

        candidate_range = candidate_max - candidate_min if candidate_max != float("inf") else 1
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
        gap = candidate_min - job_max
        gap_pct = gap / candidate_min if candidate_min > 0 else 1
        if gap_pct <= 0.1:
            return 60.0
        elif gap_pct <= 0.25:
            return 40.0
        return 20.0
