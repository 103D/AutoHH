Теперь пересмотри текущую реализацию с позиции maintainability и качества алгоритма.

НЕ добавляй новые пользовательские функции.

Текущий функционал уже достаточно большой. Следующая задача — refactoring + validation.

## 1. Большие файлы

Сейчас критически большие файлы:

* services/scoring.py
* services/matching.py
* workers/tasks/fetch_jobs.py

Не делай механическое дробление файлов.

Проанализируй ответственность каждого класса/функции и выдели реальные bounded responsibilities.

Цель:

### scoring

Разделить при необходимости:

* skill scoring;
* experience scoring;
* location scoring;
* salary scoring;
* work format scoring;
* education/language scoring;
* score aggregation.

При этом публичный API ScoringEngine должен остаться стабильным.

### matching

Отделить orchestration от domain logic.

MatchingService должен координировать pipeline, а не содержать сотни строк разных алгоритмов.

Выделить только действительно самостоятельные компоненты.

### fetch_jobs

Разделить:

* Celery task orchestration;
* source fetching;
* ingestion;
* persistence;
* source health.

Не создавай абстракции ради количества файлов.

---

# 2. Matching algorithm — важнее refactoring

Проведи audit текущего deterministic scoring.

Ответь кодом и тестами:

1. Что именно означает technical score?
2. Учитывается ли REQUIRED vs PREFERRED skill?
3. Может ли вакансия с критически отсутствующим skill получить высокий score?
4. Имеют ли skills разный вес?
5. Учитывается ли seniority?
6. Учитывается ли domain experience?
7. Учитывается ли specialization?
8. Может ли location/salary компенсировать отсутствие ключевого technical requirement?
9. Может ли LLM score исправить плохой deterministic score?
10. Есть ли upper/lower bounds?

Не переписывай scoring вслепую.

Сначала сформулируй mathematically coherent scoring model.

---

# 3. Правильная модель skills

Раздели:

REQUIRED
PREFERRED
OPTIONAL

Для skill matching:

MATCHED
PARTIAL
MISSING
UNKNOWN

Критические REQUIRED skills должны иметь значительно больший вес.

Если отсутствует критический mandatory skill, это должно быть видно в результате независимо от общего score.

Но НЕ делай каждый missing skill hard blocker.

---

# 4. LLM role

LLM должен выполнять semantic interpretation:

* extract requirements;
* classify required/preferred;
* normalize technologies;
* identify equivalents;
* identify transferable skills;
* identify seniority;
* identify domain;
* explain gaps.

Python должен выполнять:

* hard filters;
* numeric scoring;
* weights;
* thresholds;
* final score;
* recommendation.

LLM не должен произвольно присваивать финальный score.

---

# 5. Score explainability

Для каждой вакансии результат должен позволять ответить:

"Почему 78, а не 90?"

Пример:

Technical: 82
Experience: 90
Location: 95
Salary: 100
Work format: 100
Education: 70
Language: 95

И отдельно:

Required skills:

* SQL — MATCHED
* PostgreSQL — MATCHED
* Power BI — MATCHED
* DAX — MATCHED
* ClickHouse — MISSING

Preferred:

* dbt — MISSING
* Airflow — PARTIAL

Hard blockers:
none

Recommendation:
STRETCH

Такой результат должен быть доступен API.

---

# 6. Проверить специализацию

Specialization сейчас должна влиять на recommendation/resume selection, но не должна незаметно ломать базовый score.

Проверь:

DATA_ANALYST
BI_ANALYST
PRODUCT_ANALYST
RETAIL_COMMERCIAL_ANALYST

Для одной вакансии может быть несколько подходящих специализаций.

Resume selection должен выбирать лучший профиль, а не просто первый найденный.

---

# 7. Hard filters

Проверь отдельно:

experience
location
relocation
work format
employment type
salary

Hard filter должен использовать только действительно objective constraints.

Особенно проверь:

hard_experience_max_factor.

Если это бизнес-правило, сделай его явно конфигурируемым и документированным.

Если это временная эвристика — не позволяй ей скрыто определять eligibility.

---

# 8. Regression tests

После refactoring существующий behavior должен сохраниться там, где он корректен.

Добавь тесты на edge cases:

* perfect candidate;
* partial candidate;
* missing mandatory skill;
* many preferred skills but missing one required;
* junior applying to middle;
* candidate exactly at experience requirement;
* candidate below requirement;
* same city;
* different city + relocation;
* remote;
* salary overlap;
* salary missing;
* no job requirements.

Особенно протестируй границы score.

---

# 9. НЕ ломай текущие API

Публичные endpoints и schemas должны остаться backward compatible, если нет объективной причины изменить контракт.

Если schema необходимо изменить — обнови frontend и tests в той же задаче.

---

# 10. Проверка после refactoring

Запусти:

pytest
ruff
frontend typecheck
frontend build

И отдельно E2E:

manual vacancy
→ normalize
→ DB
→ hard filters
→ deterministic score
→ semantic analysis/fallback
→ final score
→ skill gaps
→ specialization
→ resume selection
→ application.

---

## Definition of Done

После этой задачи я хочу получить не больше functionality, а более качественный engine:

* меньше ответственности в отдельных файлах;
* чистый orchestration;
* deterministic scoring;
* explainable result;
* REQUIRED/PREFERRED skill semantics;
* корректный LLM boundary;
* regression tests;
* все существующие tests проходят.

Не добавляй новые providers, OAuth, Telegram features или UI features.

Сначала доведи текущий matching/ingestion engine до состояния, которое можно безопасно расширять дальше.
