# AI Job Hunter

Production-ready система автоматического поиска работы с AI-матчингом, адаптацией резюме и Telegram-уведомлениями.

## Возможности

- **Сбор вакансий** — автоматический фетчинг с HeadHunter KZ, нормализация и 3-уровневая дедупликация
- **AI-матчинг** — гибридный scoring (детерминированный + AI semantic analysis) с retry и fallback провайдером
- **Адаптация резюме** — AI-powered tailoring с anti-hallucination валидацией (запрет выдумывать опыт/навыки)
- **Cover Letter** — генерация в разных стилях, проверка фактов против профиля
- **Telegram** — уведомления с inline-кнопками (View, Prepare, Ignore) через webhook
- **Application Tracking** — 10 статусов, immutable history, статистика (interview rate, response rate)
- **Frontend** — React + TypeScript dashboard с фильтрами, Kanban и AI analysis

## Стек

| Слой | Технология |
|------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic 2 |
| Database | PostgreSQL 16 |
| Background | Celery + Redis |
| AI | OpenAI / OpenRouter (fallback) |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Infra | Docker, Docker Compose, Nginx |

## Быстрый старт

### Требования

- Docker + Docker Compose
- OpenAI API key (или OpenRouter)

### Запуск

```bash
# 1. Клонировать
git clone https://github.com/103D/AutoHH.git
cd AutoHH

# 2. Настроить окружение
cp backend/env.example backend/.env
# Отредактировать backend/.env — указать AI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# 3. Запустить все сервисы
docker compose up -d --build

# 4. Применить миграции
docker exec jobhunter-backend alembic upgrade head

# 5. Инициализировать источник вакансий
docker exec jobhunter-backend python scripts/init_hh_source.py
```

### Сервисы

| Сервис | URL | Описание |
|--------|-----|-----------|
| Frontend | http://localhost | React dashboard |
| API | http://localhost:8000 | FastAPI backend |
| Swagger | http://localhost:8000/docs | API документация |
| Health | http://localhost/health | Health check |

## Локальная разработка

### Backend

```bash
cd backend
poetry install
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev  # http://localhost:3000
```

### Тесты и линтинг

```bash
cd backend
poetry run pytest -v          # 46 тестов
poetry run ruff check app/    # линтинг
```

## Архитектура

```
AtoHH/
├── backend/
│   ├── app/
│   │   ├── api/v1/           # FastAPI routes (jobs, matching, applications, profile, telegram)
│   │   ├── core/             # config, database, logging, exceptions
│   │   ├── models/           # SQLAlchemy: Candidate, Job, MatchResult, Application, Notification
│   │   ├── schemas/          # Pydantic v2 schemas
│   │   ├── repositories/     # Data access layer (BaseRepository pattern)
│   │   ├── services/         # Business logic (scoring, matching, validation, telegram)
│   │   ├── providers/
│   │   │   ├── ai/           # AIProvider protocol + OpenAI + fallback
│   │   │   └── jobs/         # JobSource protocol + HeadHunter KZ
│   │   └── workers/          # Celery tasks + beat schedule
│   ├── alembic/              # 6 миграций
│   └── tests/                # pytest (unit + integration)
├── frontend/
│   ├── src/
│   │   ├── api/              # Axios client
│   │   ├── pages/            # Dashboard, Jobs, JobDetails, Applications, Profile
│   │   └── types/            # TypeScript interfaces
│   ├── Dockerfile            # Multi-stage (Node build → Nginx serve)
│   └── nginx.conf            # Reverse proxy + SPA + gzip + cache
├── scripts/
│   └── backup_db.sh          # PostgreSQL backup script
├── docker-compose.yml        # 7 сервисов (postgres, redis, backend, worker, beat, frontend, backup)
└── README.md
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (DB + Redis status) |
| GET | `/api/v1/jobs` | Список вакансий (фильтры: source, search, limit) |
| GET | `/api/v1/jobs/{id}` | Детали вакансии |
| POST | `/api/v1/matching/jobs/{id}/analyze` | AI-анализ вакансии |
| POST | `/api/v1/matching/resume/adapt` | Адаптация резюме |
| POST | `/api/v1/matching/resume/match` | Сопоставление резюме с вакансией |
| POST | `/api/v1/matching/cover-letter` | Генерация cover letter |
| GET | `/api/v1/applications` | Список откликов |
| POST | `/api/v1/applications` | Создать отклик |
| PATCH | `/api/v1/applications/{id}` | Обновить статус |
| GET | `/api/v1/applications/{id}/history` | История статусов |
| GET | `/api/v1/applications/statistics` | Статистика |
| GET/PUT | `/api/v1/profile` | Профиль кандидата |
| GET/POST/DELETE | `/api/v1/profile/{id}/resumes` | Версии резюме |
| POST | `/api/v1/telegram/webhook` | Telegram webhook |

## Scheduled Tasks

| Задача | Интервал | Описание |
|--------|----------|-----------|
| `fetch_jobs` | 30 мин | Сбор новых вакансий |
| `analyze_jobs` | 10 мин | AI-анализ pending вакансий |
| `send_notifications` | 5 мин | Отправка Telegram-уведомлений |

## AI Matching

Гибридный scoring:

```
final_score = deterministic_score × 0.6 + ai_score × 0.4
```

Детерминированный scoring (7 компонентов):
- **Technical** (30%) — skills/technologies overlap
- **Experience** (20%) — years match
- **Location** (10%) — location/remote
- **Salary** (10%) — salary range overlap
- **Work format** (10%) — remote/hybrid/office
- **Education** (10%) — degree requirements
- **Language** (10%) — language requirements

Рекомендации: `HIGH_PRIORITY` (90+), `APPLY` (75+), `REVIEW` (60+), `IGNORE` (<60)

## Резервное копирование

```bash
# Ручной backup
./scripts/backup_db.sh

# Автоматический — сервис db-backup в docker-compose.yml
# Запускается daily, хранит последние 7 дней
```

## Deployment

1. Указать `SECRET_KEY`, `AI_API_KEY`, `TELEGRAM_BOT_TOKEN` в `backend/.env`
2. `docker compose up -d --build`
3. `docker exec jobhunter-backend alembic upgrade head`
4. Проверить: `curl http://localhost/health`

## License

Private project.