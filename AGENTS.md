# AutoHH — AI Job Hunter

Проект: AutoHH — Dockerized job search automation system.
- Backend: Python 3.12, FastAPI, SQLAlchemy, Alembic, Celery, Poetry
- Frontend: React 18, TypeScript, Vite, Tailwind CSS
- Docker: 7 сервисов (frontend, backend, worker, beat, postgres, redis, backup)

## Структура проекта

```
AtoHH/
├── backend/          # FastAPI приложение (poetry run ...)
│   ├── app/
│   │   ├── api/v1/     # HTTP endpoints
│   │   ├── services/   # Domain services
│   │   ├── repositories/ # DB access layer
│   │   ├── models/     # SQLAlchemy models
│   │   ├── schemas/    # Pydantic schemas
│   │   ├── core/       # Config, database, logging
│   │   └── hermes/     # Internal Hermes MCP orchestrator
│   ├── tests/          # Unit tests
│   ├── alembic/        # DB migrations
│   └── scripts/        # Init scripts (init_job_sources.py, init_candidate.py, ...)
├── frontend/         # React + TypeScript (npm run ...)
│   └── src/
├── scripts/         # Shell scripts (backup_db.sh, tunnelmole-webhook.sh)
├── docker-compose*.yml
└── .hermes/         # Hermes Agent config (project.yaml, INTEGRATION.md)
```

## Как запускать

### Backend (из папки backend/)
```bash
poetry run ruff check app/       # lint
poetry run ruff format app/      # format
poetry run pytest tests/ -x -q   # tests
poetry run alembic upgrade head  # migrations
```

### Frontend (из папки frontend/)
```bash
npm run dev      # development server
npm run build    # production build (tsc + vite)
```

### Docker
```bash
docker compose ps              # status контейнеров
docker compose logs --tail=5 <service>  # логи
docker compose up -d --build   # запуск
```

### Проектные скрипты
- `scripts/backup_db.sh [container] [output_dir]` — 백업 базы данных
- `scripts/tunnelmole-webhook.sh` — настройка Telegram webhook
- `backend/scripts/init_job_sources.py` — инициализация источников вакансий
- `backend/scripts/init_candidate.py` — инициализация профиля кандидата
- `backend/scripts/create_profile_manual.py` — создание профиля вручную
- `backend/scripts/init_hh_source.py` — инициализация HH источника

## Тестирование

- Unit тесты: `poetry run pytest tests/unit/ -x -q`
- Hermes тесты: `poetry run pytest tests/unit/test_hermes_*.py -v`
- Всего Hermes тестов: 88

## Linting

- Python: `ruff check app/` / `ruff format app/`
- TypeScript: `tsc --noEmit` (встроен в `npm run build`)

## Важные файлы

- `.env` — environment variables (содержит секреты, НЕ коммитить)
- `backend/.env` — backend env (содержит секреты, НЕ коммитить)
- `frontend/.env` — frontend env
- `backend/app/main.py` — entrypoint FastAPI приложения
- `backend/app/api/v1/router.py` — маршруты API

## API Endpoints

- `GET /health` — health check
- `GET /metrics` — Prometheus metrics
- `GET /docs` — Swagger UI
- `GET/POST /api/v1/jobs` — работа с вакансиями
- `GET/POST /api/v1/matching/*` — 매칭 
- `GET/POST /api/v1/applications` — отклики

## Секреты

Секреты хранятся в `.env` файлах. Hermes Agent маскирует их в выводе.
- `.env` — общие переменные
- `backend/.env` — backend секреты (DATABASE_URL, REDIS_URL, AI_*, TELEGRAM_*, SECRET_KEY)

## Hermes Agent

Этот проект настроен для работы с Hermes Agent v0.21.1.
- Working directory: `/home/user/Projects/AtoHH`
- Timeout: 120s
- Project registry: `hermes project show autohh`

### Внутренний Hermes (backend/app/hermes/)
Не путать с внешним Hermes Agent!
- Внутренний Hermes — MCP оркестратор между GPT-5.5 и AutoHH domain services
- 3 режима автономии: READ_ONLY / ASSISTED / AUTONOMOUS
- Политика + approval gate + MCP tools
- 88 тестов

## Git

- `.hermes/cache/` и `.hermes/sessions/` игнорируются
- `.hermes/project.yaml` и `.hermes/INTEGRATION.md` отслеживаются
- `.env` и `backend/.env` игнорируются

## Hermes Agent — Multi-Model Routing

Внешний Hermes Agent v0.21.1 настроен с тремя моделями:

### Профили

| Профиль | Модель | Провайдер | Для чего |
|---------|--------|-----------|----------|
| **GPT-5.5** (default) | gpt-5.5 | openai-codex | Архитектура, debugging, сложный refactoring, анализ, финальная проверка |
| **HY3** | oc/hy3-free | custom (OmniRoute localhost:20128) | Тесты, lint, CRUD, небольшие исправления, документация, mass tasks |
| **Cline Free** | openai/gpt-4o-mini | openrouter | Бесплатный fallback, второе мнение, простые задачи |

### Fallback chain

Если GPT-5.5 недоступна:
1. HY3 (oc/hy3-free) — быстрый и дешёвый
2. Cline Free (openai/gpt-4o-mini) — бесплатный резерв

### Запуск с разными профилями

```bash
# GPT-5.5 (default, используется автоматически)
hermes chat --in /home/user/Projects/AtoHH

# Явное указание модели через CLI
hermes --provider openai-codex --model gpt-5.5 --in /home/user/Projects/AtoHH -z "task"
hermes --provider custom --model oc/hy3-free --in /home/user/Projects/AtoHH -z "task"
hermes --provider openrouter --model openai/gpt-4o-mini --in /home/user/Projects/AtoHH -z "task"

# Через скрипты (подробнее в scripts/hermes-profiles/)
./scripts/hermes-profiles/hermes-list-profiles.sh  # список профилей
./scripts/hermes-profiles/hermes-gpt55.sh chat --in .  # GPT-5.5
./scripts/hermes-profiles/hermes-hy3.sh chat --in .    # HY3
./scripts/hermes-profiles/hermes-free.sh chat --in .   # Cline Free
```

### Конфигурация

- Config: `~/.hermes/config.yaml`
- Secrets: `~/.hermes/.env` (не коммитить!)
- API keys: HERMES_CODEX_API_KEY, AI_API_KEY, OPENROUTER_API_KEY
- Провайдеры: openai-codex, custom (OmniRoute), openrouter

### Проверка

```bash
hermes config show          # текущая конфигурация
hermes fallback list        # fallback chain
hermes --version            # версия Hermes
```
