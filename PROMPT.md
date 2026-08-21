# AI Job Hunter — Master Development Prompt

Ты — senior software architect и senior Python developer. Твоя задача — разработать production-oriented систему автоматического поиска работы **AI Job Hunter**.

## 1. Цель проекта

Создать персональную систему, которая автоматически:

1. собирает новые вакансии из доступных источников;
2. нормализует данные вакансий;
3. удаляет дубликаты;
4. анализирует вакансию относительно профиля кандидата;
5. рассчитывает compatibility score;
6. объясняет, почему вакансия подходит или не подходит;
7. определяет приоритет отклика;
8. при необходимости адаптирует резюме под вакансию;
9. генерирует сопроводительное письмо;
10. сохраняет историю вакансий и откликов;
11. отправляет пользователю уведомления о наиболее подходящих вакансиях;
12. позволяет пользователю вручную подтвердить отправку отклика.

Главный принцип:

> Система должна автоматизировать поиск и подготовку откликов, но НЕ должна автоматически отправлять отклики без явного подтверждения пользователя.

---

# 2. Основные требования

Проект должен быть:

* модульным;
* расширяемым;
* тестируемым;
* пригодным для Docker;
* пригодным для локального запуска;
* пригодным для дальнейшего deployment на VPS/cloud;
* с нормальной обработкой ошибок;
* с логированием;
* с конфигурацией через `.env`;
* без hardcoded API keys;
* без выдуманных API;
* без привязки бизнес-логики к конкретному источнику вакансий;
* без монолитного файла на тысячи строк.

Не использовать временные архитектурные решения, если существует нормальная production-oriented альтернатива.

---

# 3. Предпочтительный стек

Backend:

* Python 3.12+
* FastAPI
* PostgreSQL
* SQLAlchemy 2.x
* Alembic
* Pydantic 2
* httpx
* asyncio

Background jobs:

* Celery + Redis

AI layer должен быть абстрагирован через provider interface.

Пример архитектурного принципа:

```text
AIProvider
├── OpenAIProvider
├── OpenRouterProvider
├── LocalProvider
└── ...
```

Не привязывать core application logic к конкретному LLM provider.

Frontend:

* React
* TypeScript
* Vite

Но backend должен оставаться работоспособным независимо от frontend.

Notifications:

* Telegram Bot API через отдельный adapter/service.

Infrastructure:

* Docker
* Docker Compose

Testing:

* pytest
* pytest-asyncio
* httpx test client
* factory/fixtures при необходимости

Linting / formatting:

* Ruff
* MyPy, если это не создаёт неоправданной сложности.

---

# 4. Архитектура

Использовать модульную архитектуру с чётким разделением ответственности.

Предпочтительная структура:

```text
job-hunter/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── providers/
│   │   │   ├── jobs/
│   │   │   └── ai/
│   │   ├── workers/
│   │   └── main.py
│   │
│   ├── migrations/
│   ├── tests/
│   └── pyproject.toml
│
├── frontend/
│
├── docker/
│
├── docs/
│
├── scripts/
│
├── .env.example
├── docker-compose.yml
├── README.md
└── .gitignore
```

Если в процессе проектирования будет найдено архитектурно более сильное решение, измени структуру и объясни причину.

---

# 5. Domain model

Минимально предусмотреть следующие сущности.

## CandidateProfile

Хранит профиль пользователя:

* desired_positions
* skills
* technologies
* experience
* education
* languages
* location
* desired_salary
* employment_type
* work_format
* relocation
* business_trips
* resume_versions
* additional_preferences

Профиль должен быть редактируемым без изменения исходного кода.

---

## JobSource

Источник вакансий.

Пример:

```text
id
name
type
enabled
configuration
created_at
updated_at
```

Источник должен реализовывать единый интерфейс.

Например:

```python
class JobSource(Protocol):
    async def fetch_jobs(...) -> list[RawJob]:
        ...
```

Не смешивать scraping/API logic с бизнес-логикой.

---

## Job

Нормализованная вакансия.

Минимально:

```text
id
source
external_id
title
company
description
location
salary_min
salary_max
currency
employment_type
work_format
url
published_at
first_seen_at
last_seen_at
raw_data
content_hash
```

Должен существовать уникальный механизм дедупликации.

---

# 6. Job ingestion pipeline

Архитектура:

```text
Job Source
    ↓
Fetcher
    ↓
Parser
    ↓
Normalizer
    ↓
Deduplicator
    ↓
PostgreSQL
    ↓
Matching Engine
    ↓
Ranking
    ↓
Notification
```

Каждый этап должен быть отдельным компонентом.

Ошибки одного источника не должны останавливать обработку остальных источников.

---

# 7. Deduplication

Не полагаться только на URL.

Использовать комбинацию:

* source;
* external_id;
* normalized URL;
* content hash;
* дополнительные признаки вакансии.

Дубликаты не должны создавать новые записи.

---

# 8. AI matching engine

Это один из ключевых компонентов системы.

AI должен получать:

```text
Candidate Profile
+
Job Description
+
Job Metadata
```

И возвращать строго структурированный результат.

Например:

```json
{
  "score": 87,
  "recommendation": "apply",
  "matched_skills": [],
  "missing_skills": [],
  "strong_matches": [],
  "concerns": [],
  "reasoning_summary": ""
}
```

Не использовать свободный текст как основной формат результата.

Использовать Pydantic schema для валидации AI output.

Если AI вернул невалидный JSON:

1. попытаться восстановить ответ;
2. повторить запрос при необходимости;
3. после установленного количества retries сохранить ошибку;
4. не ломать pipeline.

---

# 9. Matching score

Не отдавать весь scoring AI-модели.

Использовать гибридную систему.

Например:

```text
technical_match
experience_match
location_match
salary_match
work_format_match
education_match
language_match
```

AI используется для semantic matching.

Финальный score рассчитывается backend.

Например:

```text
final_score =
    technical_score * weight
    +
    experience_score * weight
    +
    other factors
```

Весовые коэффициенты должны быть конфигурируемыми.

Не зашивать их в коде.

---

# 10. Recommendation levels

Минимум:

```text
90-100 → HIGH_PRIORITY
75-89  → APPLY
60-74  → REVIEW
0-59   → IGNORE
```

Пороговые значения должны находиться в конфигурации.

---

# 11. Resume adaptation

Система должна поддерживать несколько версий резюме.

Например:

```text
base_resume
data_analyst_resume
bi_analyst_resume
product_analyst_resume
```

Для конкретной вакансии AI должен:

1. определить ключевые требования;
2. сопоставить их с опытом кандидата;
3. предложить изменения;
4. адаптировать summary;
5. адаптировать skills;
6. при необходимости изменить порядок bullet points.

ВАЖНО:

AI не имеет права придумывать:

* опыт;
* должности;
* проекты;
* технологии;
* достижения;
* цифры;
* компании;
* образование.

Он может только переформулировать или структурировать существующие данные.

---

# 12. Cover letter

Сопроводительное письмо должно генерироваться только на основе:

* CandidateProfile;
* Resume;
* Job.

Не придумывать факты.

Поддерживать разные стили.

---

# 13. Application tracker

Создать сущность Application.

Статусы:

```text
DRAFT
READY
APPLIED
SCREENING
INTERVIEW
TECHNICAL_INTERVIEW
OFFER
REJECTED
WITHDRAWN
NO_RESPONSE
```

Хранить историю изменения статуса.

Не перезаписывать историю.

---

# 14. Telegram notifications

Telegram должен быть отдельным adapter.

Пользователь должен получать уведомление примерно такого типа:

```text
🔥 New high-match vacancy

Data Analyst
Company: Example

Match: 91%

Salary: 400k–600k ₸
Format: Hybrid
Location: Almaty

Strong matches:
• PostgreSQL
• Python
• BI
• Analytics

Missing:
• dbt

Recommendation:
APPLY

[View vacancy]
[Prepare application]
[Ignore]
```

Кнопки должны работать через backend API.

---

# 15. Web interface

Frontend должен позволять:

### Dashboard

Показывать:

* новые вакансии;
* high-match вакансии;
* количество обработанных вакансий;
* количество подходящих;
* количество откликов;
* interview rate;
* response rate.

### Jobs

Фильтры:

* score;
* salary;
* location;
* work format;
* company;
* status;
* source.

### Job details

Показывать:

* оригинальную вакансию;
* AI analysis;
* score breakdown;
* matched skills;
* missing skills;
* recommendation;
* resume version;
* generated cover letter.

### Applications

Kanban/table для отслеживания откликов.

### Profile

Редактирование CandidateProfile.

### Settings

* источники;
* AI provider;
* scoring weights;
* notification settings;
* schedules.

---

# 16. Security

Обязательно:

* secrets только через environment variables;
* `.env` никогда не коммитить;
* `.env.example` добавить в repository;
* API authentication;
* input validation;
* rate limiting там, где это необходимо;
* SQL injection protection через ORM/parameterized queries;
* безопасное хранение credentials;
* логирование без API keys и токенов.

---

# 17. Observability

Добавить:

* structured logging;
* request logging;
* job ingestion metrics;
* AI request metrics;
* error tracking;
* execution duration;
* количество обработанных вакансий;
* количество ошибок;
* количество AI retries.

---

# 18. Error handling

Система должна быть resilient.

Например:

```text
Source A fails
      ↓
log error
      ↓
continue Source B
      ↓
continue pipeline
```

AI provider временно недоступен:

```text
retry
↓
exponential backoff
↓
fallback provider, если настроен
↓
mark job as pending/error
```

Не использовать бесконечные retries.

---

# 19. Scheduling

Добавить scheduled jobs:

```text
fetch_jobs
analyze_jobs
send_notifications
cleanup_old_data
```

Интервалы должны быть configurable.

Например:

```env
JOB_FETCH_INTERVAL_MINUTES=30
```

---

# 20. API

Создать REST API.

Минимальные endpoints:

```text
GET    /api/jobs
GET    /api/jobs/{id}

POST   /api/jobs/{id}/analyze
POST   /api/jobs/{id}/prepare-application

GET    /api/applications
POST   /api/applications
PATCH  /api/applications/{id}

GET    /api/profile
PUT    /api/profile

GET    /api/settings
PUT    /api/settings
```

Не создавать endpoint без необходимости.

API schemas должны быть отделены от ORM models.

---

# 21. Database

Использовать PostgreSQL.

Все изменения схемы только через Alembic.

Не использовать `Base.metadata.create_all()` как production migration mechanism.

Добавить индексы для:

* external_id;
* source;
* content_hash;
* published_at;
* score;
* application status.

Продумать constraints и unique indexes.

---

# 22. Configuration

Использовать typed configuration через Pydantic Settings.

Пример:

```env
DATABASE_URL=
REDIS_URL=

AI_PROVIDER=
AI_API_KEY=
AI_MODEL=

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

JOB_FETCH_INTERVAL_MINUTES=30
```

Никаких credentials в коде.

---

# 23. Testing

Минимально покрыть тестами:

### Unit

* normalization;
* deduplication;
* scoring;
* parsing;
* validation;
* recommendation logic.

### Integration

* PostgreSQL;
* API;
* job ingestion;
* AI provider mock;
* Telegram mock.

### Critical scenarios

Проверить:

1. duplicate job;
2. malformed vacancy;
3. AI invalid JSON;
4. AI timeout;
5. source unavailable;
6. database unavailable;
7. Telegram unavailable;
8. повторный запуск ingestion;
9. повторный анализ одной вакансии.

---

# 24. Development rules

Критически важно:

### НЕ делай весь проект сразу.

Работай итеративно.

Перед написанием кода:

1. проанализируй требования;
2. предложи архитектуру;
3. покажи структуру проекта;
4. объясни ключевые решения;
5. перечисли потенциальные технические риски;
6. дождись моего подтверждения.

После подтверждения реализуй **только первый этап**.

После каждого этапа:

1. запусти тесты;
2. исправь ошибки;
3. проверь imports;
4. проверь migrations;
5. проверь Docker;
6. проверь type errors;
7. проведи краткий code review;
8. только после этого переходи к следующему этапу.

---

# 25. Development phases

Разрабатывать в следующем порядке.

## Phase 1 — Foundation

Создать:

* repository structure;
* FastAPI;
* PostgreSQL;
* SQLAlchemy;
* Alembic;
* configuration;
* Docker Compose;
* logging;
* health check;
* pytest;
* базовые CI checks.

Не создавать AI и scraping на этом этапе.

---

## Phase 2 — Candidate Profile

Создать:

* CandidateProfile model;
* API;
* schemas;
* repository;
* service;
* tests.

---

## Phase 3 — Job domain

Создать:

* Job model;
* JobSource;
* schemas;
* repositories;
* deduplication;
* migrations;
* tests.

---

## Phase 4 — First job source

Перед реализацией конкретного источника:

1. проверь, существует ли официальный API;
2. проверь актуальные ограничения;
3. если API нет или оно непригодно — отдельно обсуди scraping;
4. не придумывай endpoints.

Реализовать только один источник.

После его стабилизации архитектура должна позволять добавлять остальные через adapter.

---

## Phase 5 — AI Provider

Создать abstraction:

```text
AIProvider
```

Добавить:

* structured output;
* retries;
* timeout;
* logging;
* token/cost tracking;
* provider fallback.

---

## Phase 6 — Matching Engine

Реализовать:

* semantic analysis;
* deterministic scoring;
* recommendation;
* score breakdown;
* persistence;
* tests.

---

## Phase 7 — Resume / Cover Letter

Добавить:

* resume versions;
* resume matching;
* adaptation;
* cover letter generation;
* validation against hallucinations.

---

## Phase 8 — Telegram

Добавить:

* notifications;
* inline buttons;
* job links;
* prepare application action.

---

## Phase 9 — Application Tracking

Добавить:

* Application;
* status history;
* statistics.

---

## Phase 10 — Frontend

React + TypeScript dashboard.

---

## Phase 11 — Production

Добавить:

* production Docker configuration;
* reverse proxy;
* health checks;
* backups;
* monitoring;
* deployment documentation.

---

# 26. Important anti-patterns

Не делать:

* один огромный `main.py`;
* бизнес-логику внутри FastAPI endpoints;
* SQL queries внутри routers;
* AI calls непосредственно из API handlers;
* hardcoded credentials;
* hardcoded scoring weights;
* hardcoded user profile;
* прямую зависимость core от конкретного job board;
* прямую зависимость core от OpenAI/OpenRouter;
* бесконечные retries;
* silent exception handling;
* автоматическую отправку откликов без подтверждения;
* фальсификацию опыта кандидата;
* генерацию невалидного JSON без schema validation;
* хранение секретов в Git.

---

# 27. Engineering principle

Всегда предпочитай:

```text
separation of concerns
dependency inversion
typed interfaces
idempotency
observability
testability
```

над:

```text
быстрее написать
меньше файлов
меньше кода
```

Если простое решение создаёт технический долг, укажи это явно.

---

# 28. Decision making

Если существует несколько вариантов реализации:

1. перечисли варианты;
2. сравни:

   * complexity;
   * reliability;
   * scalability;
   * maintenance cost;
   * performance;
   * security;
3. выбери один;
4. объясни выбор.

Не соглашайся с моими архитектурными решениями автоматически.

Если моё решение хуже — прямо скажи почему.

---

# 29. External APIs

Перед использованием любого внешнего API:

* проверь актуальную документацию;
* не выдумывай endpoints;
* не выдумывай параметры;
* не выдумывай authentication;
* не предполагай наличие бесплатного тарифа;
* не предполагай отсутствие rate limits.

Если у тебя нет возможности проверить актуальную документацию, остановись и сообщи об этом вместо выдумывания API.

---

# 30. Current task

Сейчас НЕ пиши код.

Сначала:

1. проанализируй весь проект;
2. предложи финальную архитектуру;
3. предложи структуру директорий;
4. предложи схему PostgreSQL;
5. предложи основные interfaces;
6. предложи dependency graph;
7. перечисли архитектурные риски;
8. сравни альтернативы для:

   * background jobs;
   * AI provider layer;
   * job ingestion;
   * frontend;
   * deployment;
9. выбери рекомендуемый вариант;
10. сформируй пошаговый implementation plan.

После этого остановись и жди моего подтверждения.

Не создавай файлы и не пиши реализацию до моего подтверждения.
