
"# Project Checkpoint - Job Hunter

**Last Updated**: 2026-08-13
**Phase**: 5/7 Complete
**Status**: Foundation + CRUD + Jobs + Provider + Workers Ready

## What Works

### Services Running
```bash
# Docker containers
docker ps --filter name=jobhunter

# Expected: postgres + redis
```

### Database
```bash
# Tables: candidate_profiles, job_sources, jobs, alembic_version
docker exec jobhunter-postgres psql -U jobhunter -d jobhunter -c '\\dt'

# HeadHunter source initialized
docker exec jobhunter-postgres psql -U jobhunter -d jobhunter -c 'SELECT name, type, enabled FROM job_sources;'
```

### Tests
```bash
cd backend
poetry run pytest tests/test_health.py tests/test_deduplication.py tests/test_hh_provider.py -v
# Known: Event loop teardown errors (test infrastructure, not application code)
```

### API
```bash
# Start server
DATABASE_URL='postgresql+asyncpg://jobhunter:password@localhost:5432/jobhunter' \
REDIS_URL='redis://localhost:6379/0' \
AI_API_KEY='test' \
poetry run uvicorn app.main:app --reload

# Endpoints
curl http://localhost:8000/health
curl http://localhost:8000/docs
```

## Key Architecture Decisions

### 1. Database
- PostgreSQL with asyncpg driver
- SQLAlchemy 2.0 async ORM
- Alembic migrations
- Models: CandidateProfile, Job, JobSource
- All tables use UUID primary keys + timestamps

### 2. Deduplication (Job Model)
Three-level check:
1. `source_id + external_id` (from job board)
2. `content_hash` (SHA256: title + company + description + location)
3. `url_normalized` (cleaned URL, tracking params removed)

### 3. Provider Pattern
- Protocol-based interface (`JobSourceProvider`)
- HeadHunter KZ implemented (hh.ru API compatible)
- Configuration in database (JSONB)
- Easy to add new providers

### 4. Background Jobs
- Celery + Redis
- Worker + Beat containers
- Periodic fetching (configurable interval)
- Task: `fetch_jobs_from_all_sources`

### 5. Code Style
- Repository pattern for data access
- Service layer for business logic
- Pydantic schemas for validation
- Ruff for linting (line-length: 100, Python 3.12)

## Known Issues

### 1. Test Event Loop Errors
```
RuntimeError: Task got Future attached to a different loop
```
- Cause: asyncpg connection pool created at import time
- Affects: tests after first test in suite
- Impact: Test infrastructure only, production works fine
- Fix needed: Dispose engine between tests

### 2. Alembic Migration Tracking
- Tables created manually after migration sync issue
- Version: `293aaf4729a6` marked as applied
- Tables: `job_sources`, `jobs` created via SQL
- All good now, migrations will work going forward

### 3. Environment Variables
- Can't create `.env` files (security restriction)
- Solution: Use environment variables directly
- See: `backend/env.example` for reference

## Next Steps

### Phase 6: AI Matching Engine
Not started. Will include:
- OpenAI/OpenRouter integration
- Job-Candidate matching logic
- Score calculation
- Recommendation generation

### Phase 7: Application Management
Not started. Will include:
- Application model
- Status tracking
- Telegram notifications

## Critical Files

```
backend/
├── app/
│   ├── core/
│   │   ├── config.py          # Pydantic settings
│   │   ├── database.py        # Async engine + session
│   │   └── exceptions.py      # Custom exceptions
│   ├── models/
│   │   ├── candidate.py       # CandidateProfile
│   │   └── job.py             # Job, JobSource
│   ├── repositories/
│   │   ├── base.py            # Generic CRUD
│   │   ├── candidate.py
│   │   └── job.py
│   ├── services/
│   │   ├── candidate.py
│   │   ├── job.py
│   │   └── deduplication.py   # 3-level dedup
│   ├── providers/
│   │   └── jobs/
│   │       └── hh_kz.py       # HeadHunter API
│   ├── workers/
│   │   ├── celery_app.py
│   │   └── tasks/
│   │       ├── fetch_jobs.py
│   │       └── analyze_jobs.py
│   ├── utils/
│   │   └── hash.py            # URL norm + content hash
│   └── main.py                # FastAPI app
├── alembic/versions/          # Migrations
├── tests/
│   ├── conftest.py            # Test fixtures
│   ├── test_health.py
│   ├── test_candidate_profile.py
│   ├── test_deduplication.py
│   └── test_hh_provider.py
└── pyproject.toml             # Poetry deps
```

## Quick Recovery Commands

```bash
# Start services
docker start jobhunter-postgres jobhunter-redis

# Check migrations
cd backend && poetry run alembic current

# Run tests
poetry run pytest -v --tb=short

# Start API
DATABASE_URL='postgresql+asyncpg://jobhunter:password@localhost:5432/jobhunter' \
REDIS_URL='redis://localhost:6379/0' \
AI_API_KEY='test' \
poetry run uvicorn app.main:app --reload

# Manual job fetch (when workers running)
docker exec jobhunter-worker celery -A app.workers.celery_app call fetch_jobs_from_all_sources
```

## Token Optimization Notes

When continuing:
1. Read only files you need to modify
2. Use `grep_search` for finding patterns
3. Use `read_file_range` for large files
4. Trust existing tests - don't rerun without changes
5. Reference this checkpoint before asking about architecture"