"""Canonical input fingerprints for reproducible matching analyses.

The module is deliberately pure and persistence-agnostic.  It snapshots only
fields that can affect hard filters, deterministic scoring, semantic extraction
or recommendation.  Secrets, contact details and arbitrary provider metadata
are excluded by construction.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from app.services.skill_taxonomy import CANONICAL_SKILLS, SKILL_ALIASES

ENGINE_VERSION = "match-v3"
TAXONOMY_VERSION = "taxonomy-v1"

_CANDIDATE_FIELDS = (
    "desired_positions",
    "skills",
    "technologies",
    "skills_metadata",
    "experience_years",
    "experience_level",
    "experience",
    "projects",
    "certifications",
    "education",
    "languages",
    "location",
    "relocation_possible",
    "business_trips_acceptable",
    "desired_salary_min",
    "desired_salary_max",
    "salary_currency",
    "employment_types",
    "work_formats",
)

_JOB_FIELDS = (
    "title",
    "company",
    "description",
    "location",
    "salary_min",
    "salary_max",
    "currency",
    "employment_type",
    "work_format",
    "experience_required",
    "specializations",
)

_SCORING_FIELDS = (
    "score_weight_technical",
    "score_weight_experience",
    "score_weight_location",
    "score_weight_salary",
    "score_weight_work_format",
    "score_weight_education",
    "score_weight_language",
    "score_required_skill_weight",
    "score_preferred_skill_weight",
    "score_optional_skill_weight",
    "score_missing_required_penalty",
    "hard_filters_enabled",
    "hard_experience_max_factor",
    "hard_experience_max_gap",
    "hard_salary_tolerance",
    "threshold_dream_job",
    "threshold_stretch",
    "threshold_solid_match",
    "threshold_market_research",
    "threshold_learning",
    "stretch_experience_min_factor",
    "stretch_experience_max_factor",
    "stretch_max_missing_skills",
    "stretch_salary_max_increase",
    "llm_gate_enabled",
    "llm_gate_min_deterministic_score",
)


def _read(obj: Any, field: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(field)
    return getattr(obj, field, None)


def _canonicalize(value: Any) -> Any:
    """Return a JSON-compatible, recursively stable representation."""
    if value is None or isinstance(value, bool | int | float | str):
        return value.strip() if isinstance(value, str) else value
    if isinstance(value, Enum):
        return _canonicalize(value.value)
    if isinstance(value, UUID | date | datetime):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    if is_dataclass(value):
        return _canonicalize(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list | tuple | set | frozenset):
        normalized = [_canonicalize(item) for item in value]
        return sorted(normalized, key=_canonical_json)
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def _fingerprint(value: Any) -> str:
    payload = _canonical_json(_canonicalize(value)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _snapshot(obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return _canonicalize({field: _read(obj, field) for field in fields})


def candidate_snapshot(profile: Any) -> dict[str, Any]:
    """Snapshot every candidate field used by matching and hard filters."""
    return _snapshot(profile, _CANDIDATE_FIELDS)


def job_snapshot(job: Any) -> dict[str, Any]:
    """Snapshot normalized vacancy fields that affect matching."""
    return _snapshot(job, _JOB_FIELDS)


def scoring_snapshot(settings_obj: Any) -> dict[str, Any]:
    """Snapshot all configured deterministic scoring/recommendation rules."""
    return _snapshot(settings_obj, _SCORING_FIELDS)


def taxonomy_fingerprint() -> str:
    """Fingerprint the actual canonical skill and alias dictionaries."""
    return _fingerprint(
        {
            "canonical_skills": CANONICAL_SKILLS,
            "skill_aliases": SKILL_ALIASES,
        }
    )


def build_match_provenance(
    profile: Any,
    job: Any,
    settings_obj: Any,
    *,
    engine_version: str = ENGINE_VERSION,
    taxonomy_version: str = TAXONOMY_VERSION,
) -> dict[str, str]:
    """Build component fingerprints and the final matching input identity."""
    candidate_fingerprint = _fingerprint(candidate_snapshot(profile))
    job_fingerprint = _fingerprint(job_snapshot(job))
    scoring_fingerprint = _fingerprint(scoring_snapshot(settings_obj))
    taxonomy_hash = taxonomy_fingerprint()
    prompt_version = str(_read(settings_obj, "prompt_version") or "")

    analysis_fingerprint = _fingerprint(
        {
            "candidate_fingerprint": candidate_fingerprint,
            "job_fingerprint": job_fingerprint,
            "scoring_fingerprint": scoring_fingerprint,
            "taxonomy_fingerprint": taxonomy_hash,
            "taxonomy_version": taxonomy_version,
            "engine_version": engine_version,
            "prompt_version": prompt_version,
        }
    )
    return {
        "candidate_fingerprint": candidate_fingerprint,
        "job_fingerprint": job_fingerprint,
        "scoring_fingerprint": scoring_fingerprint,
        "taxonomy_fingerprint": taxonomy_hash,
        "taxonomy_version": taxonomy_version,
        "engine_version": engine_version,
        "prompt_version": prompt_version,
        "analysis_fingerprint": analysis_fingerprint,
    }


__all__ = [
    "ENGINE_VERSION",
    "TAXONOMY_VERSION",
    "build_match_provenance",
    "candidate_snapshot",
    "job_snapshot",
    "scoring_snapshot",
    "taxonomy_fingerprint",
]
