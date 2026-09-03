Теперь продолжай реализацию AutoHH. Предыдущий промпт считай архитектурным ТЗ. Не переписывай его и не начинай новый проект — работай непосредственно с текущим кодом репозитория.

Главная цель: получить реально работающий end-to-end pipeline, а не набор абстракций и TODO.

## 1. Сначала проверь текущее состояние

Перед изменениями:

* проверь git diff;
* проверь существующие модели, миграции, API, services, providers, workers и tests;
* определи, что из предыдущего ТЗ уже реализовано;
* не дублируй уже существующий функционал;
* найди все TODO, stub, NotImplementedError, mock/fake providers и места, где система формально работает, но не получает реальные данные.

После этого сразу переходи к реализации, не останавливайся на отчёте.

---

# 2. КРИТИЧЕСКИЙ ПРИОРИТЕТ — получение реальных вакансий

Сейчас главная проблема AutoHH — приложение фактически не имеет надёжного источника вакансий.

Сделай ingestion pipeline реально рабочим.

Архитектура:

JobSource
→ fetch
→ raw response
→ normalize
→ validate
→ deduplicate
→ persist
→ matching queue

Каждый provider должен быть изолирован от остального приложения.

Сделай:

* JobSource protocol/interface;
* provider registry;
* provider health/status;
* timeout;
* retry;
* exponential backoff;
* rate-limit handling;
* structured logging;
* обработку malformed responses;
* provider-specific exceptions;
* idempotent ingestion;
* source + external_job_id UNIQUE constraint;
* возможность отключить неисправный provider без падения всей системы.

Не делай один глобальный try/except вокруг всего pipeline.

---

# 3. Не привязывай архитектуру к HH

HH должен быть provider'ом, а не фундаментом всей системы.

Создай/доведи до рабочего состояния:

* HeadHunter provider;
* другие provider'ы только если есть легальный и технически пригодный API/source;
* Manual Import provider.

ВАЖНО:

Не реализовывай обход CAPTCHA, авторизации, антибота, rate-limit или других механизмов защиты.

Если API какого-либо источника недоступен, реализуй provider interface + корректный disabled/unavailable state и продолжай работу остальных частей системы.

Не создавай fake вакансии для имитации работы.

---

# 4. Сделай Manual Import

Это обязательный fallback.

Пользователь должен иметь возможность добавить вакансию:

* через API;
* через frontend;
* желательно из URL;
* через JSON/text payload.

Нормализуй её в тот же Job model, который используется реальными providers.

После manual import вакансия должна проходить абсолютно тот же pipeline:

normalize
→ dedup
→ persist
→ matching
→ recommendation.

Таким образом AutoHH можно полноценно тестировать даже при отсутствии API HH.

---

# 5. Реальный Matching Engine

Не превращай matching в один вызов LLM.

Раздели:

### Hard filters

Например:

* location;
* work format;
* salary;
* required experience;
* employment type;
* language;
* обязательные технологии, если они действительно mandatory.

### Soft scoring

Используй:

* technical match;
* experience match;
* domain match;
* seniority;
* business relevance;
* salary;
* location;
* work format;
* education;
* language.

Все веса должны быть конфигурируемыми.

LLM используется только там, где он действительно нужен:

* semantic skill matching;
* extraction требований;
* определение синонимов;
* определение implicit requirements;
* explanation gap'ов;
* классификация вакансии.

LLM НЕ должен быть единственным источником итогового score.

---

# 6. Skill Taxonomy

Создай нормализованный skill taxonomy.

Например:

PostgreSQL
SQL
Power BI
DAX
Python
pandas
FastAPI

должны иметь aliases/synonyms.

Не сравнивай просто строки:

"Postgres" != "PostgreSQL"

Это должна быть нормальная domain model.

Состояния:

MATCHED
PARTIAL
MISSING

Для каждого mismatch должна существовать причина.

---

# 7. Четыре карьерных профиля

Не делай четыре независимых резюме, которые потом расходятся.

Должен существовать:

Master Candidate Profile

и specialization profiles:

DATA_ANALYST
BI_ANALYST
PRODUCT_ANALYST
RETAIL_COMMERCIAL_ANALYST

Каждый профиль должен определять:

* headline;
* summary;
* preferred skills;
* specialization;
* preferred industries;
* scoring modifiers;
* resume version;
* keywords.

Matching должен понимать, какой профиль лучше подходит под вакансию.

Например retail vacancy должна естественно получать высокий score для RETAIL_COMMERCIAL_ANALYST.

---

# 8. Resume Recommendation

Для каждой вакансии система должна уметь ответить:

"Какую версию резюме лучше использовать?"

Алгоритм:

job requirements
→ candidate profile
→ specialization
→ skill overlap
→ resume profile
→ recommendation.

Не генерируй новое резюме каждый раз без необходимости.

Сначала выбери наиболее подходящий существующий профиль.

---

# 9. Anti-hallucination

Это критично.

AI никогда не должен добавлять в резюме:

* несуществующий опыт;
* технологии;
* компании;
* должности;
* проекты;
* метрики;
* образование;
* сертификаты.

Любое утверждение должно быть traceable до Candidate Profile / Resume Profile.

Если AI предлагает unsupported claim — validation должен его отклонить.

---

# 10. Feedback Loop

Application должна хранить:

* vacancy;
* selected resume;
* match score;
* applied_at;
* status;
* rejection/invitation/interview/offer;
* timestamps;
* source;
* relevant matching features.

История статусов immutable.

На основании накопленных данных система должна в будущем иметь возможность определить:

* какие вакансии дают ответы;
* какие skills коррелируют с приглашениями;
* какие источники лучше;
* какие специализации работают лучше;
* какие score thresholds слишком строгие/мягкие.

Не делай ML ради ML. Сначала собирай качественные данные.

---

# 11. Celery / Workers

Проверь, что pipeline реально работает через workers:

fetch jobs
→ analyze
→ match
→ notify.

Никаких silent failures.

Ошибки worker'ов должны быть:

* logged;
* retried where appropriate;
* visible через monitoring/status;
* безопасны для повторного запуска.

Операции ingestion и analysis должны быть idempotent.

---

# 12. API

Проверь API end-to-end.

Минимально должны работать:

GET /jobs
GET /jobs/{id}

POST /jobs/manual

POST /matching/analyze
POST /matching/match
POST /matching/adapt
POST /matching/cover-letter

GET /applications
POST /applications
PATCH /applications/{id}/status
GET /applications/{id}/history
GET /applications/statistics

GET /profile
PUT /profile

GET /resume-versions
POST /resume-versions

Добавь нормальную validation/error handling.

Не возвращай внутренние exceptions клиенту.

---

# 13. Database

Проверь индексы и constraints.

Особенно:

* source + external_job_id;
* job status;
* created_at;
* application status;
* candidate ownership;
* foreign keys;
* cascade behavior;
* uniqueness.

Не создавай N+1 queries.

Для списков используй pagination.

---

# 14. Security

Особенно важно для HH OAuth.

OAuth access token:

* никогда не передаётся LLM;
* никогда не хранится во frontend;
* никогда не попадает в logs;
* не возвращается API клиенту;
* хранится encrypted/securely;
* используется только соответствующим provider adapter.

LLM должен получать только необходимые normalized данные.

---

# 15. Frontend

После backend implementation проверь frontend.

Главный пользовательский сценарий должен выглядеть так:

Candidate
→ подключает источник
→ получает вакансии
→ видит match score
→ открывает вакансию
→ видит почему match высокий/низкий
→ видит matched/partial/missing skills
→ видит рекомендуемый профиль резюме
→ может добавить вакансию вручную
→ может создать application
→ отслеживает статус.

Не делай красивый UI поверх неработающего backend.

---

# 16. Tests

Не ограничивайся unit tests.

Обязательно:

### Unit

* scoring;
* skill normalization;
* dedup;
* hard filters;
* resume validation.

### Provider contract tests

Каждый JobSource должен соответствовать единому контракту.

### Integration

* DB;
* ingestion;
* manual import;
* matching;
* application lifecycle.

### E2E

Создай тестовый сценарий:

manual vacancy
→ normalize
→ persist
→ match candidate
→ select resume
→ create application
→ status update
→ history.

После этого этот сценарий должен проходить полностью.

---

# 17. Observability

Добавь structured logs и понятные identifiers:

request_id
job_id
source
external_job_id
candidate_id
application_id
provider
operation.

Ошибку вида "something went wrong" считать недостаточной.

---

# 18. Docker

Проверь:

docker compose up

должен поднимать весь необходимый stack.

Проверь:

* backend;
* PostgreSQL;
* Redis;
* Celery worker;
* Celery beat;
* frontend;
* migrations.

Fresh environment должен подниматься без ручного редактирования Python-файлов.

---

# 19. Definition of Done

Не считай задачу завершённой потому, что код написан.

Задача считается завершённой только если ты можешь доказать:

1. БД создаётся.
2. Миграции применяются.
3. Backend запускается.
4. Worker запускается.
5. Реальный или manual JobSource создаёт вакансии.
6. Вакансия сохраняется.
7. Dedup работает.
8. Matching работает.
9. Skill gaps рассчитываются.
10. Подбирается resume profile.
11. Application создаётся.
12. Status history сохраняется.
13. Frontend получает эти данные.
14. Tests проходят.
15. Docker stack запускается.
16. Повторный ingestion не создаёт duplicate jobs.

---

# 20. Очень важное правило работы

Работай итеративно.

После каждого крупного этапа:

1. внеси изменения;
2. запусти тесты;
3. запусти lint/type checks;
4. проверь реальные API endpoints;
5. исправь ошибки;
6. только потом переходи дальше.

Не оставляй систему в состоянии "это должно работать".

Если обнаруживаешь архитектурную проблему — исправляй первопричину, а не добавляй workaround поверх workaround.

Если внешний API недоступен, не блокируй весь проект: реализуй fallback/manual provider и продолжай.

В конце каждого этапа показывай:

* что реализовано;
* какие файлы изменены;
* какие тесты запущены;
* результаты тестов;
* что осталось;
* какие внешние зависимости реально недоступны.

Продолжай самостоятельно до максимально полного рабочего состояния. Не останавливайся после первого найденного TODO.
