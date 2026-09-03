# Задача: Production-реструктуризация и развитие AutoHH

Ты работаешь над существующим репозиторием **103D/AutoHH**.

Твоя задача — не переписать проект с нуля, а провести полноценный аудит текущей реализации и затем постепенно улучшить приложение до production-ready архитектуры.

## Главный принцип

Сначала изучи существующий код и архитектуру.

**Не начинай писать код сразу.**

Сначала:

1. изучи структуру репозитория;
2. изучи README;
3. найди entrypoints;
4. изучи модели данных;
5. изучи JobSource protocol и providers;
6. изучи текущую реализацию HeadHunter;
7. изучи ingestion pipeline;
8. изучи matching engine;
9. изучи Candidate / Job / MatchResult / Application;
10. изучи работу с PostgreSQL;
11. изучи конфигурацию и environment variables;
12. изучи тесты;
13. найди TODO, FIXME и потенциальные технические долги.

После этого составь краткий технический аудит:

* текущая архитектура;
* что уже сделано хорошо;
* критические проблемы;
* проблемы масштабируемости;
* проблемы надёжности;
* проблемы безопасности;
* проблемы тестируемости;
* где архитектура уже предусмотрела расширение, но оно не реализовано;
* что необходимо изменить;
* что менять не следует.

**Только после аудита приступай к реализации.**

---

# 1. Главная архитектурная цель

AutoHH должен быть не «HH-клиентом», а платформой автоматизированного поиска работы.

HH должен быть только одним из источников вакансий.

Целевая архитектура:

```text
                    JOB SOURCES
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
    HeadHunter         Other           Manual
      Provider        Providers         Import
        │                │                │
        └────────────────┼────────────────┘
                         ▼
                 Source Normalizer
                         │
                         ▼
                    Deduplication
                         │
                         ▼
                    PostgreSQL
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        Matching Engine        AI Analysis
              │                     │
              └──────────┬──────────┘
                         ▼
                  Recommendation
                         │
                         ▼
                 Resume Selection
                         │
                         ▼
                  Application
                         │
                         ▼
                 Outcome Tracking
                         │
                         ▼
                  Feedback Loop
```

Существующий `JobSource` protocol сохрани, если он действительно соответствует этой архитектуре.

Не создавай вторую конкурирующую абстракцию.

---

# 2. JobSource должен быть настоящей abstraction boundary

Все источники вакансий должны возвращать единую внутреннюю модель вакансии.

Источник не должен знать:

* как работает matching;
* как работает LLM;
* как выбирается резюме;
* как сохраняются application;
* как считается статистика.

Пример концептуального интерфейса:

```text
JobSource
    fetch(...)
        ↓
Raw external vacancy
        ↓
Normalizer
        ↓
Domain Job
```

Если существующий интерфейс уже решает эту задачу — не переписывай его без необходимости.

---

# 3. HeadHunter не должен быть single point of failure

Сейчас основная проблема приложения — зависимость от HH API.

Не делай архитектуру, в которой:

```text
HH unavailable
      ↓
application unusable
```

Должно быть:

```text
HH unavailable
      ↓
provider reports unavailable
      ↓
other providers continue
      ↓
manual import remains available
```

При этом:

**НЕ реализовывай обход ограничений HH, CAPTCHA, авторизации или иных механизмов защиты.**

Не используй scraping, если это противоречит правилам соответствующего источника.

Используй официальные API/разрешённые способы получения данных.

---

# 4. Provider Registry

Создай или улучши registry источников.

Концептуально:

```text
JobSourceRegistry
    register(source)
    get(name)
    enabled()
```

Добавление нового источника должно требовать создания только нового provider и его регистрации.

Не должно требоваться изменение matching engine.

---

# 5. Надёжность ingestion

Pipeline получения вакансий должен быть:

```text
fetch
 ↓
validate
 ↓
normalize
 ↓
deduplicate
 ↓
persist
```

Каждая стадия должна иметь понятную ответственность.

Добавь:

* timeout;
* retry только для retryable ошибок;
* exponential backoff;
* structured logging;
* provider health/status;
* обработку rate limits;
* обработку malformed responses;
* graceful degradation.

Не делай бесконечные retry.

---

# 6. Идемпотентность

Один и тот же job не должен создавать десятки записей.

Определи стабильный внешний идентификатор:

```text
source
external_job_id
```

Используй его для deduplication.

Если источник не предоставляет стабильный ID, используй аккуратный deterministic fingerprint.

Добавь соответствующий database constraint.

---

# 7. Нормализация вакансий

Внутренняя `Job` должна быть независима от HH.

Минимально необходимо нормализовать:

```text
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
experience_required
published_at
url
skills
raw_data
```

`raw_data` можно сохранять для повторного анализа, если это допустимо с точки зрения условий конкретного источника.

Не передавай provider-specific поля по всей системе.

---

# 8. Matching Engine

Текущий matching engine нужно сохранить как основу, но пересмотреть его логику.

Нельзя считать один общий score единственным источником истины.

Раздели:

## Hard requirements

Например:

* обязательный опыт;
* location;
* формат работы;
* employment;
* обязательные требования;
* другие объективные ограничения.

Если hard requirement критически не выполнен:

```text
NOT_ELIGIBLE
```

а не просто:

```text
score = 40
```

---

# 9. Soft matching

После прохождения hard filter рассчитывай:

```text
technical_match
experience_match
domain_match
business_match
tool_match
education_match
language_match
work_format_match
```

Затем итоговый score.

Весы должны быть конфигурируемыми, а не hardcoded по всему проекту.

Например:

```text
MatchingProfile
    weights
    thresholds
    hard_requirements
```

---

# 10. Не превращай LLM в генератор случайного score

LLM не должен единолично решать:

```text
"this candidate is 83%"
```

LLM лучше использовать для:

* semantic skill matching;
* определения эквивалентных навыков;
* извлечения требований;
* классификации вакансии;
* определения специализации;
* анализа gaps;
* объяснения результата.

Финальный score должен быть воспроизводимым настолько, насколько это возможно.

Сохраняй:

```text
score
component_scores
matched_requirements
missing_requirements
hard_failures
reasoning_summary
model
prompt_version
```

Это необходимо для дебага и последующего feedback loop.

---

# 11. Специализация вакансии

Добавь классификацию вакансий.

Минимальные категории:

```text
DATA_ANALYST
BI_ANALYST
PRODUCT_ANALYST
RETAIL_COMMERCIAL_ANALYST
```

Допускается:

```text
MULTI_LABEL
```

если вакансия относится одновременно к нескольким категориям.

Не делай классификацию только по title.

Используй:

* title;
* description;
* requirements;
* skills;
* domain.

---

# 12. Четыре профиля резюме

Приложение должно поддерживать несколько версий резюме.

Создай концепцию:

```text
ResumeProfile
```

Минимум:

```text
DATA_ANALYST
BI_ANALYST
PRODUCT_ANALYST
RETAIL_COMMERCIAL_ANALYST
```

Каждый профиль должен содержать:

```text
profile_name
headline
summary
skills
experience
projects
specialization_keywords
```

При этом фактический опыт кандидата не должен дублироваться вручную в четырёх местах.

Используй:

```text
Master Candidate Profile
          ↓
Resume Profiles
```

---

# 13. Master Candidate Profile

Создай единственный источник истины для кандидата.

Он должен хранить:

```text
experience
education
skills
technologies
domains
projects
achievements
languages
certifications
```

Каждый skill должен иметь metadata:

```text
skill
category
confidence
experience_level
production_experience
years
```

Например концептуально:

```text
PostgreSQL
    category: database
    production: true

Python
    category: programming
    production: true

Power BI
    category: BI
    production: ...
```

Не придумывай значения.

---

# 14. Skill taxonomy

Создай нормализованный skill layer.

Например:

```text
PostgreSQL
postgres
Postgres
```

должны распознаваться как один skill.

То же самое для:

```text
Power BI
PowerBI
Microsoft Power BI
```

Но не объединяй технологии, которые только кажутся похожими.

Например:

```text
PostgreSQL != MySQL
Power BI != Tableau
DAX != SQL
```

Добавь aliases только там, где соответствие действительно корректно.

---

# 15. Gap Analysis

Для каждой вакансии система должна уметь показывать:

```text
MATCHED
PARTIAL
MISSING
```

Например:

```text
SQL                 MATCHED
PostgreSQL           MATCHED
Power BI             MATCHED
DAX                  PARTIAL
Cohort Analysis      MISSING
Retail Analytics     MATCHED
```

Важно:

`MISSING` не обязательно означает `NOT_ELIGIBLE`.

Это skill gap.

---

# 16. Resume Recommendation

После matching:

```text
vacancy
    ↓
specialization
    ↓
matching
    ↓
best resume profile
```

Например:

```text
Retail vacancy
    ↓
RETAIL_COMMERCIAL_ANALYST
    ↓
cv_retail
```

Система должна объяснять выбор:

```text
Recommended profile:
Retail / Commercial Data Analyst

Reason:
- retail domain experience
- branch analytics
- inventory analysis
- SQL/PostgreSQL
- operational KPI
```

---

# 17. Feedback Loop

Используй существующие `Application` / response tracking, если они уже есть.

Система должна собирать:

```text
vacancy
match_score
resume_profile
applied_at
response
rejection
interview
offer
```

В будущем это позволит анализировать:

```text
Which score range produces interviews?
Which resume profile performs better?
Which specialization performs better?
Which missing skills correlate with rejection?
```

Но НЕ реализуй ML-рекомендации до появления достаточного объёма данных.

Сначала просто собирай качественные события.

---

# 18. Ranking

Добавь несколько уровней:

```text
HIGH_PRIORITY
APPLY
REVIEW
SKIP
```

Пороговые значения должны быть конфигурацией.

Не размазывай числа по коду.

---

# 19. Search strategy

Поиск должен поддерживать:

```text
query
location
salary
experience
work_format
employment
specialization
```

И позволять запускать несколько поисковых профилей.

Например:

```text
Data Analyst Алматы
BI Analyst Алматы
Product Analyst Алматы
Retail Data Analyst Алматы
```

Не зашивай эти значения непосредственно в provider.

---

# 20. Database

Проверь текущую схему PostgreSQL.

Особое внимание:

* foreign keys;
* unique constraints;
* indexes;
* timestamps;
* enum/status design;
* nullable fields;
* migrations;
* cascading;
* query performance.

Добавь индексы только на основании реальных access patterns.

Не создавай десятки ненужных индексов.

---

# 21. Security

Проверь:

* API keys;
* OAuth credentials;
* provider credentials;
* `.env`;
* logs;
* database credentials;
* user data;
* resume data.

Никакие secrets не должны попадать:

* в git;
* в logs;
* в API responses;
* в exception messages.

Проверь `.gitignore`.

Если секрет уже попал в git history — сообщи об этом отдельно.

---

# 22. Observability

Добавь нормальные structured logs.

Каждая задача ingestion должна иметь correlation/request ID.

Например:

```text
source=hh
operation=fetch_jobs
query=data analyst
status=success
jobs_received=42
jobs_new=17
jobs_duplicate=25
duration_ms=...
```

Ошибки должны позволять определить:

```text
provider
operation
error type
retry count
request id
```

Не логируй credentials или полный персональный профиль.

---

# 23. Testing

Не ограничивайся unit tests.

Минимальная структура:

```text
unit tests
integration tests
provider tests
matching tests
database tests
```

Особенно протестировать:

### Matching

```text
perfect match
partial match
hard requirement failure
missing skill
domain mismatch
salary mismatch
location mismatch
```

### Deduplication

```text
same source + external_id
same vacancy repeated
different sources
```

### Providers

Использовать fixtures/mocks.

Тесты не должны зависеть от живого HH API.

---

# 24. Contract tests для providers

Каждый provider должен гарантировать:

```text
raw external vacancy
        ↓
valid normalized Job
```

Добавь тесты, которые проверяют обязательные поля.

Это позволит добавлять новые источники без риска сломать matching.

---

# 25. Manual Import

Manual import должен остаться полноценным fallback.

Минимум:

```text
URL
title
description
company
location
salary
```

Если пользователь вставляет текст вакансии, система должна уметь:

```text
text
 ↓
parser
 ↓
normalized Job
 ↓
matching
```

Это позволит тестировать весь pipeline даже при отсутствии API.

---

# 26. API

Проверь существующие endpoints.

Раздели:

```text
sources
jobs
search
matching
resumes
applications
analytics
```

API не должен содержать бизнес-логику provider'ов.

Business logic должна находиться в services/use-cases/domain layer в соответствии с текущей архитектурой проекта.

Не создавай чрезмерный Clean Architecture boilerplate.

---

# 27. Не ломать существующий API без необходимости

Если endpoint уже используется frontend:

* сохрани совместимость;
* либо добавь versioning;
* либо сделай migration.

Не меняй контракт только ради красоты.

---

# 28. Performance

Особое внимание:

* N+1 queries;
* повторному вызову LLM;
* повторному анализу одной вакансии;
* duplicate jobs;
* массовому matching;
* unnecessary API calls.

Используй caching там, где это оправдано.

Например:

```text
same vacancy
+
same candidate profile
+
same prompt version
=
можно переиспользовать analysis
```

---

# 29. AI cost control

LLM не должен вызываться на каждую вакансию без необходимости.

Pipeline:

```text
Source
 ↓
Normalization
 ↓
Hard Filter
 ↓
Deterministic Matching
 ↓
only ambiguous/relevant jobs
 ↓
LLM
```

Это существенно уменьшит стоимость и latency.

---

# 30. Resume adaptation

В дальнейшем приложение должно уметь адаптировать выбранное резюме под вакансию.

Но:

**НЕ выдумывать опыт.**

LLM может:

* менять порядок skills;
* менять summary;
* выбирать релевантные achievements;
* выбирать подходящие проекты;
* адаптировать формулировки.

LLM НЕ может:

* добавлять несуществующий опыт;
* добавлять fake metrics;
* придумывать production experience;
* менять реальные даты;
* добавлять технологии без подтверждения.

---

# 31. Что НЕ делать

Не надо:

* переписывать весь backend;
* менять framework без необходимости;
* добавлять микросервисы;
* добавлять Kafka;
* добавлять Redis только потому, что это «production»;
* добавлять Kubernetes;
* добавлять ML без данных;
* создавать огромную абстракцию ради одной функции;
* копировать Clean Architecture из учебника;
* добавлять scraping HH для обхода API-ограничений;
* хранить секреты в коде;
* делать LLM единственным источником истины.

Приоритет:

```text
correctness
>
reliability
>
maintainability
>
performance
>
complexity
```

---

# 32. План реализации

Работай поэтапно.

## Phase 0 — Audit

Ничего не менять.

Выдать:

```text
Architecture map
Critical issues
Technical debt
Recommended changes
Risk assessment
```

## Phase 1 — Job ingestion

Исправить:

* JobSource;
* provider isolation;
* normalization;
* deduplication;
* retries;
* provider health;
* manual import.

## Phase 2 — Matching

Переделать:

* hard filters;
* component scores;
* configurable weights;
* specialization;
* skill matching;
* gap analysis.

## Phase 3 — Candidate / Resume system

Добавить:

* Master Candidate Profile;
* 4 Resume Profiles;
* resume selection.

## Phase 4 — Feedback

Добавить:

* application outcomes;
* statistics;
* feedback dataset.

## Phase 5 — Optimization

После появления данных:

* ranking optimization;
* adaptive thresholds;
* analytics;
* cost optimization.

---

# 33. Правило работы

После каждого этапа:

1. запусти тесты;
2. исправь regression;
3. проверь миграции;
4. проверь API;
5. проверь существующий frontend;
6. проверь lint/type checks;
7. покажи изменённые файлы;
8. покажи, что именно изменилось;
9. покажи оставшийся technical debt.

Не переходи к следующему этапу, если предыдущий находится в сломанном состоянии.

---

# 34. Самое важное

Не предполагай, что описанная выше архитектура обязательно лучше существующей.

Сначала сравни её с текущей.

Если существующий код уже решает задачу лучше — сохрани существующее решение.

Если обнаружишь архитектурное противоречие, остановись и объясни:

```text
Current design:
...

Proposed design:
...

Why change is necessary:
...

Migration risk:
...

Recommended approach:
...
```

Не делай большие destructive changes без необходимости.

---

# 35. Первый результат от тебя

Сейчас НЕ пиши код.

Сделай полный аудит репозитория AutoHH и верни:

## 1. Current Architecture

Краткая схема компонентов и зависимостей.

## 2. Critical Problems

P0 / P1 / P2.

## 3. Current Job Pipeline

От получения вакансии до сохранения и matching.

## 4. HH Dependency Analysis

Точно определить:

* где приложение зависит от HH;
* где возникают ошибки;
* где можно сделать fallback;
* что можно исправить без HH API;
* что требует credentials/API access.

## 5. Matching Analysis

Разобрать текущую формулу и предложить изменения.

## 6. Resume Architecture

Как встроить:

```text
Master CV
    ↓
4 specialized profiles
```

## 7. Migration Plan

Пошаговый план без переписывания проекта.

## 8. Tests

Каких тестов сейчас не хватает.

## 9. Technical Debt

Отдельный список.

## 10. Recommendation

Назвать один рекомендуемый вариант архитектуры и объяснить, почему он лучше альтернатив.

**После аудита остановись и жди подтверждения.**

Не вноси изменения до моего подтверждения.
