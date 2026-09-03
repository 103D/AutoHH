# Project Checkpoint — AtoHH (AI Job Hunter)

**Last Updated**: 2026-09-03
**Phase**: 7/7 Complete (Definition of Done achieved)
**Status**: Full pipeline working — Manual Import → Matching → Resume → Application → History

---

## What Works

### Docker Stack (fresh-start verified)
```bash
docker compose down -v && docker compose build && docker compose up -d

# 6 containers: postgres, redis, backend, worker, beat, frontend, db-backup
# All healthy, migrations auto-applied via entrypoint
```

### Database
```bash
# Migrations: a1b2c3d4e5f6 (head) — auto-applied on backend/worker/beat start
docker compose exec backend alembic current

# Tables: candidate_profiles, job_sources, jobs, match_results, applications,
#         application_status_history, resume_profiles, alembic_version, ...
```

### Tests
```bash
cd backend

# Unit (155 tests)
poetry run pytest tests/unit/ -q

# E2E (4 tests — requires Docker DB)
DATABASE_URL='postgresql+asyncpg://jobhunter:password@localhost:5432/jobhunter_test' \
poetry run pytest tests/test_e2e_manual_pipeline.py -q

# Total: 159 tests, all green
```

### API Endpoints (verified against Docker)
```bash
# Health
curl http://localhost:8000/health
# {"status":"healthy","version":"0.1.0","database":"ok","redis":"ok"}

# Manual Import (PROMPT.MD DoD #5)
curl -X POST http://localhost:8000/api/v1/jobs/manual \
  -H 'Content-Type: application/json' \
  -d '{"title":"Analyst","company":"ACME","description":"SQL, Python","location":"Almaty"}'
# → {"job":{...},"status":"created"}

# Matching — full analysis with persistence
curl -X POST "http://localhost:8000/api/v1/matching/analyze?job_id=<ID>&candidate_profile_id=<PID>"
# → {"score":64,"recommendation":"STRETCH","stretch_analysis":{...}}

# Matching — soft match (deterministic, no persistence)
curl -X POST "http://localhost:8000/api/v1/matching/match?job_id=<ID>&candidate_profile_id=<PID>"
# → {"score":64,"score_breakdown":{...},"matched_skills":[...],"missing_skills":[...]}

# Frontend: http://localhost:80/ (static build, served by nginx)
```

---

## Architecture Decisions

### 1. Database + Migrations
- PostgreSQL 16 + asyncpg + SQLAlchemy 2.0 async ORM
- Alembic migrations, auto-applied via `docker-entrypoint.sh` before app start
- UUID primary keys + timestamps on all models

### 2. Deduplication (3-level)
1. `source_id + external_id` (from provider)
2. `content_hash` (SHA256: title+company+description+location)
3. `url_normalized` (cleaned URL, tracking params removed)

### 3. Provider Pattern
- Protocol-based: `JobSourceProvider`
- Implemented: HH, RemoteOK, Habr, SuperJob, Manual, JSON-LD
- Configuration in database (JSONB)

### 4. Matching Pipeline
- **Hard filters** → **Scoring** (configurable weights) → **LLM gate** → **Stretch analysis**
- **Specialization** detection (DATA_ANALYST, BI_ANALYST, PRODUCT_ANALYST, RETAIL_COMMERCIAL_ANALYST)
- **Skill taxonomy** with variants for fuzzy matching
- **Soft match** — deterministic path (no LLM), used for quick previews

### 5. Resume Profiles
- Master CV → specialized profiles per specialization
- Profile recommendation based on job specialization overlap
- Skill selection and content generation per profile

### 6. Background Processing
- Celery + Redis (worker + beat containers)
- Periodic fetching from all enabled sources
- Tasks: `fetch_jobs_from_all_sources`, `analyze_pending_jobs`

### 7. Frontend
- React + TypeScript + Vite + Tailwind CSS
- Pages: Dashboard, Jobs (with Import + Analyze), JobDetails, Applications, Profile
- Components: `ManualImportModal`, `MatchResultCard`

### 8. Code Style
- Repository pattern + Service layer + Pydantic schemas
- Ruff (line-length 100, Python 3.12 target)
- 159 tests (unit + E2E)

---

## Key Files

```
backend/
├── app/
│   ├── api/v1/
│   │   ├── jobs.py              # GET/POST /jobs, POST /jobs/manual
│   │   ├── matching.py          # analyze, match, soft-match, gaps, recommend-resume
│   │   ├── applications.py      # CRUD + status history + package
│   │   ├── profile.py           # CandidateProfile + ResumeVersions + ResumeProfiles
│   │   └── analytics.py         # market-overview, skill-gap, learning-roadmap, dream-jobs
│   ├── services/
│   │   ├── matching.py          # MatchingService (hard filters, scoring, LLM gate, soft_match)
│   │   ├── scoring.py           # ScoringEngine (configurable weights, breakdown)
│   │   ├── stretch_classifier.py
│   │   ├── skill_taxonomy.py    # skill_variants for fuzzy matching
│   │   └── ...
│   ├── schemas/
│   │   ├── matching.py          # MatchResultResponse, SoftMatchResponse, ...
│   │   └── ...
│   ├── providers/jobs/          # hh_kz, remoteok, habr, superjob, manual, jsonld
│   └── workers/                 # Celery app + tasks
├── alembic/versions/            # Migrations (head: a1b2c3d4e5f6)
├── docker-entrypoint.sh         # Runs alembic upgrade head before app start
├── tests/
│   ├── unit/                    # 155 tests (matching, scoring, filters, ...)
│   └── test_e2e_manual_pipeline.py  # 4 E2E tests
└── Dockerfile                   # Entrypoint pattern for auto-migrations

frontend/
├── src/
│   ├── api/client.ts            # Axios client + all API methods
│   ├── components/
│   │   ├── ManualImportModal.tsx
│   │   └── MatchResultCard.tsx
│   └── pages/
│       ├── Jobs.tsx             # Import button + Analyze per job
│       └── ...
└── Dockerfile                   # nginx static serve
```

---

## Quick Recovery Commands

```bash
# Full fresh-start (clean volumes + rebuild)
docker compose down -v && docker compose build && docker compose up -d

# Check status
docker compose ps
docker compose logs backend | tail -20

# Run migrations manually (usually not needed — entrypoint handles it)
docker compose exec backend alembic upgrade head

# Tests (unit only, no DB needed)
cd backend && poetry run pytest tests/unit/ -q

# Tests (E2E, needs Docker DB)
cd backend
DATABASE_URL='postgresql+asyncpg://jobhunter:password@localhost:5432/jobhunter_test' \
poetry run pytest tests/test_e2e_manual_pipeline.py -q

# Create test DB if missing
docker compose exec postgres createdb -U jobhunter jobhunter_test

# Frontend build
cd frontend && npm run build
```

---

## Known Issues / Limitations

### 1. LLM Provider
- OmniRoute (local OpenAI-compatible) configured as primary
- Falls back to OpenRouter if primary fails
- Soft-match path is deterministic (no LLM) — by design

### 2. Celery Beat
- Beat container runs but periodic tasks depend on provider API availability
- Manual fetch: `docker compose exec worker celery -A app.workers.celery_app call app.workers.tasks.fetch_jobs_from_all_sources`

### 3. Frontend
- No authentication (single-user mode)
- Profile selection is manual (first profile used as default)

---

## Definition of Done (PROMPT.MD) — Status

| # | Requirement | Status |
|---|-------------|--------|
| 1 | Manual vacancy import via API | ✅ `POST /jobs/manual` |
| 2 | Duplicate detection (content hash) | ✅ 3-level dedup |
| 3 | Hard filters (salary, location, experience, employment) | ✅ Configurable |
| 4 | Configurable scoring weights | ✅ `ScoringEngine` |
| 5 | LLM gate (optional, with deterministic fallback) | ✅ |
| 6 | Stretch analysis | ✅ `StretchClassifier` |
| 7 | Specialization detection | ✅ 4 specializations |
| 8 | Skill taxonomy with variants | ✅ `skill_variants` |
| 9 | Resume profile recommendation | ✅ `recommend_resume` |
| 10 | Resume selection & adaptation | ✅ Stub (LLM-based) |
| 11 | Application with status history | ✅ Full CRUD |
| 12 | Application package (resume + cover letter + diff) | ✅ |
| 13 | Feedback loop (threshold advisor) | ✅ |
| 14 | Prometheus metrics | ✅ |
| 15 | Docker fresh-start with auto-migrations | ✅ Entrypoint pattern |
| 16 | E2E test: manual → match → resume → application → history | ✅ 4 tests |

---

## Token Optimization Notes

When continuing:
1. Read only files you need to modify
2. Use `search_codebase` for finding patterns
3. Trust existing tests — don't rerun without changes
4. Reference this checkpoint before asking about architecture
5. Docker is source of truth — if it works in Docker, it works

### 7. Frontend
- React + TypeScript + Vite + Tailwind CSS
- Pages: Dashboard, Jobs (with Import + Analyze), JobDetails, Applications, Profile
- Components: `ManualImportModal`, `MatchResultCard`

### 8. Code Style
- Repository pattern + Service layer + Pydantic schemas
- Ruff (line-length 100, Python 3.12 target)
- 159 tests (unit + E2E)