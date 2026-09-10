# AutoHH (AI Job Hunter)

Dockerized система автоматического поиска работы с гибридным матчингом (детерминированный + опциональный AI), трекингом откликов и веб-дашбордом.

## Что работает из коробки

| Фича | Статус | Комментарий |
|------|--------|-------------|
| **Manual import вакансий** | ✅ Готов | Через API или фронтенд |
| **RemoteOK fetching** | ✅ Готов | Публичное API, не требует ключей |
| **Детерминированный matching** | ✅ Готов | 7 компонентов, hard filters, stretch detection |
| **Application Tracking** | ✅ Готов | 10 статусов, immutable history, статистика |
| **Gap Analysis** | ✅ Готов | matched / missing skills без LLM |
| **Resume selection** | ✅ Готов | Выбор лучшего резюме под вакансию |
| **Docker Compose стек** | ✅ Готов | 7 сервисов, health checks, auto-migrations |
| **Frontend** | ✅ Готов | React 18 + Vite, фильтры, Kanban, детали |
| **HeadHunter KZ / Remote** | 🔑 Требует регистрации | Нужен App ID с https://dev.hh.ru/ |
| **AI Semantic Analysis** | 🔑 Требует API key | OpenAI / OpenRouter / OmniRoute |
| **Telegram бот** | 🔑 Требует Bot Token | Webhook, inline-кнопки, входящие ссылки/резюме, /score и /train |
| **Habr Career** | ❌ Scraper устарел | Отключён по умолчанию |
| **Zarplata** | ❌ Scraper устарел | Отключён по умолчанию |
| **SuperJob** | 🔑 Требует API key | Отключён по умолчанию |

В ingestion factory зарегистрировано **7 типов источников**: `hh_kz`,
`hh_remote`, `remote_ok`, `manual`, `habr_career`, `zarplata`, `superjob`.
`hh_kz` и `hh_remote` отвечают только за сбор публичных вакансий. Они не
представляют аккаунт соискателя и не выполняют действия от его имени.

## Стек

| Слой | Технология |
|------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic 2, Celery |
| Database | PostgreSQL 16 |
| Cache / Broker | Redis 7 |
| AI (опционально) | OpenAI, OpenRouter, OmniRoute |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Infra | Docker, Docker Compose, Nginx |

## Быстрый старт

### Требования

- Docker + Docker Compose
- (Опционально) OpenAI / OpenRouter API key для AI-анализа
- (Опционально) Telegram Bot Token для уведомлений и приёма ссылок/резюме через бота
- (Для HH) Зарегистрированное приложение на https://dev.hh.ru/

### Запуск

```bash
# 1. Клонировать
git clone https://github.com/103D/AutoHH.git
cd AutoHH

# 2. Настроить окружение
cp backend/env.example backend/.env
# Отредактировать backend/.env:
#   - SECRET_KEY (обязательно в production)
#   - AI_API_KEY / OPENROUTER_API_KEY (опционально)
#   - TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (опционально)
#   - HH_USER_AGENT — заменить на зарегистрированный (опционально)

# 3. Запустить
docker compose up -d --build

# 4. Инициализировать источники вакансий
# По умолчанию включены: RemoteOK, Manual, HeadHunter (если HH_USER_AGENT настроен)
# Отключены: Habr Career, Zarplata, SuperJob
docker exec jobhunter-backend python scripts/init_job_sources.py
```

### Сервисы

| Сервис | URL | Описание |
|--------|-----|----------|
| Frontend | http://localhost | React dashboard |
| API | http://localhost:8000 | FastAPI backend |
| Swagger | http://localhost:8000/docs | OpenAPI документация |
| Health | http://localhost:8000/health | DB + Redis status |
| Metrics | http://localhost:8000/metrics | Prometheus (если включён) |

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
npm run dev   # http://localhost:5173
```

### Тесты и линтинг

```bash
cd backend
poetry run pytest -v           # 182+ тестов
poetry run ruff check app/     # линтинг
```

## Архитектура

```
AtoHH/
├── backend/
│   ├── app/
│   │   ├── api/v1/           # FastAPI routes
│   │   │   ├── jobs.py       # CRUD + manual import + sources
│   │   │   ├── matching.py   # analyze, soft-match, gaps, recommend-resume
│   │   │   ├── applications.py # CRUD + status history + stats
│   │   │   ├── profile.py    # Candidate profile
│   │   │   ├── resumes.py    # Resume profile versions
│   │   │   ├── telegram.py   # Webhook + inline buttons
│   │   │   └── analytics.py  # Metrics / metrics proxy
│   │   ├── core/             # config, database, logging, metrics
│   │   ├── models/           # SQLAlchemy ORM
│   │   ├── schemas/          # Pydantic v2
│   │   ├── repositories/     # BaseRepository pattern
│   │   ├── services/         # matching, scoring, dedup, hard_filters, validation
│   │   ├── providers/
│   │   │   ├── ai/           # OpenAI, OpenRouter, CachedAIProvider
│   │   │   └── jobs/         # 8 job providers (see table below)
│   │   └── workers/          # Celery tasks: fetch_jobs, analyze_jobs, notifications
│   ├── alembic/              # Миграции (auto-applied в Docker)
│   └── tests/                # pytest unit + e2e
├── frontend/
│   ├── src/
│   │   ├── api/              # Axios client
│   │   ├── pages/            # Dashboard, Jobs, JobDetails, Applications, Profile
│   │   └── types/            # TypeScript interfaces
│   ├── Dockerfile            # Multi-stage (Node → Nginx)
│   └── nginx.conf            # Reverse proxy + SPA fallback
├── docker-compose.yml        # 7 сервисов
└── scripts/
    ├── init_job_sources.py   # Инициализация провайдеров
    └── backup_db.sh          # PostgreSQL backup
```

## Job Providers

| Провайдер | Тип | Требования | Статус |
|-----------|-----|-----------|--------|
| HeadHunter KZ | API | Регистрация на dev.hh.ru + HH_USER_AGENT | 🔑 Credentials |
| HeadHunter Remote | API | То же + `schedule=remote` | 🔑 Credentials |
| RemoteOK | API | Нет | ✅ Работает |
| Habr Career | Scraper (JSON-LD) | — | ❌ Устарел (отключён) |
| Zarplata | Scraper (JSON-LD) | — | ❌ Устарел (отключён) |
| SuperJob | API | API key (X-api-app-id) | 🔑 Credentials |
| Manual | In-memory | — | ✅ Работает |

Провайдеры с ошибками автоматически отключаются после 5 consecutive failures.

## Matching (v2)

### Детерминированный scoring (работает без AI)

7 компонентов с настраиваемыми весами (нормализуются к 1.0):

| Компонент | Вес | Описание |
|-----------|-----|----------|
| Technical | 30% | Пересечение skills / technologies |
| Experience | 20% | Соответствие лет опыта |
| Location | 10% | Город / remote / relocation |
| Salary | 10% | Пересечение диапазонов (с tolerance) |
| Work format | 10% | remote / hybrid / office |
| Education | 10% | Уровень образования |
| Language | 10% | Языковые требования |

### Hard Filters (task spec #8)

Критические несоответствия дают `NOT_ELIGIBLE` вместо низкого score:
- Опыт: vacancy требует > 1.5× кандидата
- Формат: office-only при отказе от офиса
- Локация: другой город без relocation и без remote
- Тип занятости: не из списка кандидата
- Зарплата: max < min кандидата с tolerance 20%

### Категории рекомендаций

| Категория | Score | Описание |
|-----------|-------|----------|
| DREAM_JOB | 85+ | Идеальное совпадение |
| STRETCH | 70–84 | Нужно поднабрать скиллов |
| SOLID_MATCH | 55–69 | Хорошее совпадение |
| MARKET_RESEARCH | 40–54 | Слабое совпадение |
| LEARNING | 25–39 | Для обучения |
| NOT_ELIGIBLE | — | Hard filter failed |

### AI-матчинг (опционально)

LLM не назначает итоговый numeric score. Актуальный pipeline:

```text
Hard filters
→ deterministic component scoring
→ optional LLM requirement/equivalence extraction
→ deterministic re-score по извлечённой семантике
→ recommendation и explainable gaps
```

Финальная арифметика, веса, caps и thresholds всегда выполняются Python-кодом.
Поле `score` в legacy AI response не участвует в расчёте результата.

AI вызывается только если:
- Hard filters пройдены
- Детерминированный score ≥ 40 (LLM Gate, настраивается)

При сбое AI — graceful fallback на детерминированный score.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (DB + Redis) |
| GET | `/api/v1/jobs` | Список вакансий (pagination, filters) |
| POST | `/api/v1/jobs` | Создать вакансию (manual import) |
| GET | `/api/v1/jobs/{id}` | Детали вакансии |
| POST | `/api/v1/matching/match` | Soft-match (deterministic only, no persistence) |
| POST | `/api/v1/matching/jobs/{id}/analyze` | Full analyze + persist |
| POST | `/api/v1/matching/jobs/{id}/recommend-resume` | Лучшее резюме под вакансию |
| GET | `/api/v1/matching/jobs/{id}/gaps` | Skill gap analysis |
| POST | `/api/v1/matching/resume/adapt` | Адаптация резюме (AI, опционально) |
| POST | `/api/v1/matching/cover-letter` | Генерация cover letter (AI, опционально) |
| GET | `/api/v1/applications` | Список откликов |
| POST | `/api/v1/applications` | Создать отклик |
| PATCH | `/api/v1/applications/{id}` | Обновить статус |
| GET | `/api/v1/applications/{id}/history` | История статусов |
| GET | `/api/v1/applications/statistics` | Статистика (interview rate, response rate) |
| GET/PUT | `/api/v1/profile` | Профиль кандидата |
| GET/POST/DELETE | `/api/v1/profile/{id}/resumes` | Версии резюме |
| POST | `/api/v1/telegram/webhook` | Telegram webhook: callback-кнопки + входящие сообщения (ссылка → импорт и оценка, резюме → профиль, /score, /train) |

## Scheduled Tasks

| Задача | Интервал | Описание |
|--------|----------|----------|
| `fetch_jobs` | 30 мин | Сбор вакансий из enabled sources |
| `analyze_jobs` | 10 мин | AI-анализ pending вакансий (если AI включён) |
| `send_notifications` | 5 мин | Отправка Telegram-уведомлений |

## Резервное копирование

```bash
# Ручной backup
./scripts/backup_db.sh

# Автоматический — сервис db-backup в docker-compose
# Запускается daily, хранит последние 7 дней
```

## Deployment

Основной `docker-compose.yml` предназначен для **локальной разработки**: он
публикует PostgreSQL/Redis и монтирует `./backend:/app` для быстрого цикла
разработки. Не используйте его как production-конфигурацию на публичном VPS.

Для production используйте отдельный compose-файл:

```bash
cp .env.production.example .env.production
# заполнить все значения без placeholder-ов
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

Production Compose:

- не публикует PostgreSQL и Redis наружу;
- не монтирует исходный код в контейнеры;
- не содержит hardcoded паролей;
- требует явные `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `DATABASE_URL`,
  `REDIS_URL` и `SECRET_KEY`;
- публикует только frontend HTTP-порт, который следует размещать за внешним
  TLS reverse proxy.

После запуска:

```bash
curl http://localhost/health
docker compose --env-file .env.production -f docker-compose.prod.yml \
  exec backend python scripts/init_job_sources.py
```

Архитектурные решения по HH account integration и versioned matching описаны в
`backend/docs/adr/001-hh-account-integration.md` и
`backend/docs/adr/002-versioned-matching.md`.

## License

Private project.
