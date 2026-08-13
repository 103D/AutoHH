# AI Job Hunter

AI-powered job hunting automation system.

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.12+ (for local development)

### Setup

1. Clone repository
2. Copy environment file:
```bash
cp backend/env.example backend/.env
```

3. Edit `backend/.env` with your credentials:
   - Database credentials (default works for Docker)
   - AI provider API key (OpenAI or OpenRouter)
   - Telegram bot token (optional)

4. Start services:
```bash
docker-compose up -d
```

5. Run migrations:
```bash
docker-compose exec backend alembic upgrade head
```

6. Check health:
```bash
curl http://localhost:8000/health
```

## Development

### Local Setup (without Docker)

```bash
cd backend
poetry install
poetry shell
```

### Run migrations
```bash
alembic upgrade head
```

### Start server
```bash
uvicorn app.main:app --reload
```

### Run tests
```bash
pytest
```

### Code quality
```bash
ruff check .
ruff format .
```

## Project Status

**Phase 1: Foundation** ✅
- FastAPI setup
- PostgreSQL + Alembic
- Configuration management
- Logging
- Docker Compose
- Health check
- Basic tests

**Next Phase**: Candidate Profile CRUD

## Architecture

```
API Layer (FastAPI)
    ↓
Service Layer (Business Logic)
    ↓
Repository Layer (Database Access)
    ↓
PostgreSQL
```

Background jobs via Celery + Redis (coming in Phase 5).

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc# AutoHH
