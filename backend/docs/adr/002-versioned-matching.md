# ADR-002: Versioned and reproducible matching results

- Status: Proposed
- Date: 2026-09-06

## Context

`match_results` currently has a unique index on `(job_id,
candidate_profile_id)`. A row does not record which candidate facts, resume,
job content, scoring configuration, taxonomy or semantic extraction produced
its score. After any input changes, callers cannot know whether the result is
current or reproduce why an older score was different.

The existing LLM cache already fingerprints part of a job/profile plus
`prompt_version`, but it is not a persisted match provenance model and omits
multiple deterministic inputs.

## Decision

Make match analyses append-only and identify an analysis by a deterministic
input fingerprint. Keep a separate notion of the current result.

```text
Candidate snapshot/fingerprint
Resume profile/version fingerprint
Job snapshot/fingerprint
Scoring config version + fingerprint
Skill taxonomy version + fingerprint
Requirement extractor/prompt version
Engine version
  -> analysis_fingerprint
  -> immutable MatchResult revision
```

### Required provenance columns

- `revision` — monotonic per `(job_id, candidate_profile_id,
  resume_profile_id)`;
- nullable `resume_profile_id` and future `resume_version_id`;
- `candidate_fingerprint`;
- `resume_fingerprint`;
- `job_fingerprint`;
- `scoring_fingerprint`;
- `taxonomy_version` and `taxonomy_fingerprint`;
- `extractor_version` / `prompt_version`;
- `engine_version`;
- `analysis_fingerprint` (unique);
- `superseded_at` or `is_current` maintained transactionally;
- existing score, breakdown, LLM metadata and `analyzed_at` remain immutable.

### Fingerprint inputs

Candidate fingerprint must include every field used by hard filters or scoring:
skills, technologies, skill metadata, experience, level, education, languages,
location, relocation, salary, employment types and work formats.

Job fingerprint must include normalized title/description/requirements,
location, salary, currency, employment/work format, experience requirement and
specializations. `jobs.content_hash` alone is insufficient unless its canonical
payload is expanded to all matching inputs.

Scoring fingerprint must include component weights, required/preferred/optional
weights, missing-required penalty, hard-filter settings, category thresholds
and stretch settings.

All JSON is canonicalized with sorted keys and stable list normalization before
SHA-256 hashing. Secrets and LLM cost metadata are never fingerprint inputs.

### Read/write semantics

- Before analysis, compute `analysis_fingerprint`.
- If an identical successful revision exists, return it without LLM/scoring.
- Otherwise create a new immutable revision in one transaction and mark the
  previous current revision superseded.
- Default GET endpoints return current results only.
- History endpoint returns revisions and provenance.
- `analyze_pending_jobs` skips only when a current revision has the same input
  fingerprint; the mere existence of any old row is not enough.
- User recommendation override belongs to a separate override/audit entity or
  explicitly targets a revision; it must not mutate historical computed data.

### Schema rollout

1. Add nullable provenance columns and non-unique supporting indexes.
2. Backfill legacy rows as `engine_version='legacy'`, with unknown fingerprints.
3. Add `revision` and populate `1` for legacy rows.
4. Replace unique `(job_id, candidate_profile_id)` with a partial unique current
   index covering job/candidate/resume identity.
5. Change repository reads to `current only` and writes to append revisions.
6. Add history API and stale/current fields without breaking existing response
   fields.
7. After backfill verification, enforce non-null fingerprints for new rows.

### Concurrency

Two workers may analyze the same inputs simultaneously. The unique
`analysis_fingerprint` plus transactional current-index update is the source of
truth; one worker reuses the winner after an integrity conflict.

## Consequences

- Scores become reproducible and stale results detectable.
- Multiple resume profiles can have independent current matches for one job.
- Storage grows; retention may archive old revisions but must not silently
  rewrite history linked to applications.
- Application records should pin the exact match revision and resume version
  used at apply time.

## Delivery milestones

1. Pure canonical snapshot/fingerprint module with characterization tests.
2. Additive migration and legacy backfill.
3. Append-only repository methods and concurrency tests.
4. MatchingService reuse/invalidation logic.
5. API current/history semantics and frontend stale indicator.
6. Pin Application to match revision/resume version and extend feedback reports.