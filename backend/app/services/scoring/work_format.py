"""Work format score component (match model v3)."""

from app.models.candidate import CandidateProfile
from app.models.job import Job


def work_format_score(candidate: CandidateProfile, job: Job) -> float:
    cand_formats = [fmt.lower() for fmt in (candidate.work_formats or []) if fmt]

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
