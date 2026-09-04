"""Location score component (match model v3)."""

from app.models.candidate import CandidateProfile
from app.models.job import Job

# Same-city candidates are treated as co-located; a short list of KZ cities
# is compared explicitly so cross-city candidates are scored honestly.
KZ_CITIES = {
    "almaty", "astana", "nur-sultan", "shymkent", "aktau",
    "atyrau", "karaganda", "тараз", "актобе",
}


def location_score(candidate: CandidateProfile, job: Job) -> float:
    if not candidate.location and not job.location:
        return 50.0

    candidate_loc = (candidate.location or "").lower()
    job_loc = (job.location or "").lower()

    cand_formats = [f.lower() for f in (candidate.work_formats or []) if f]
    cand_relocation = bool(candidate.relocation_possible)

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
        if candidate_loc in KZ_CITIES and job_loc in KZ_CITIES:
            if candidate_loc == job_loc:
                return 95.0
            if not cand_relocation:
                return 30.0
            return 60.0

    if cand_relocation:
        return 75.0

    return 20.0
