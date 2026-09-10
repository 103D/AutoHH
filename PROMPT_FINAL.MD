Ты работаешь непосредственно в существующем репозитории AutoHH.

Твоя задача — не написать демонстрационный прототип и не добавить несколько поверхностных AI-функций, а довести существующую систему до production-ready состояния как полноценный AI Career Optimization Engine.

Ключевое требование:

НЕ ПЕРЕПИСЫВАЙ ПРОЕКТ С НУЛЯ.

Сначала тщательно проанализируй существующую архитектуру, модели, API, frontend, services, database schema, тесты и текущие бизнес-процессы. Переиспользуй существующие компоненты там, где это архитектурно оправдано.

Перед изменением кода составь краткий технический план с:

1. текущей архитектурой;
2. уже существующими возможностями;
3. что необходимо переиспользовать;
4. что необходимо изменить;
5. какие новые компоненты нужны;
6. какие потенциальные архитектурные проблемы обнаружены;
7. порядок реализации.

Не делай вид, что функциональность существует, если её фактически нет.

==================================================

1. ЦЕЛЬ
   ==================================================

AutoHH должен стать системой полного цикла:

Candidate Profile
→ Resume Intelligence
→ Job Intelligence
→ Candidate/Job Matching
→ Resume Optimization
→ Application
→ Outcome Tracking
→ Feedback Analytics
→ Market Intelligence

Система должна отвечать не только на вопрос:

"Подходит ли кандидат вакансии?"

но и:

"Насколько хорошо резюме представляет кандидата?"
"Что мешает пройти ATS?"
"Какие требования вакансии не доказаны резюме?"
"Какие части резюме необходимо изменить?"
"Какие изменения разрешены на основании реальных фактов кандидата?"
"Какая версия резюме с большей вероятностью даст интервью?"
"Какие изменения реально повышают response/interview rate?"

==================================================
2. SOURCE OF TRUTH
==================

Главный принцип системы:

НИКАКИХ ВЫДУМАННЫХ КОМПЕТЕНЦИЙ.

LLM никогда не должен иметь возможность самостоятельно добавлять:

* технологии;
* навыки;
* должности;
* достижения;
* цифры;
* обязанности;
* проекты;
* компании;
* сертификаты;
* образование;
* опыт;
* бизнес-результаты.

Источником истины являются структурированные данные Candidate Profile / Resume Profile и подтвержденные пользователем факты.

Если LLM предлагает утверждение, которого нет среди подтвержденных фактов:

→ пометить как unsupported claim;
→ не включать автоматически в финальное резюме;
→ предложить пользователю подтвердить факт.

Существующий механизм validation / anti-hallucination обязательно изучить и расширить, а не дублировать без необходимости.

==================================================
3. RESUME INTELLIGENCE
======================

Добавь полноценный слой Resume Intelligence поверх существующих resume_parser / resume_profile.

Он должен анализировать:

A. Structure

* контактные данные;
* summary;
* experience;
* education;
* skills;
* projects;
* languages;
* certifications;
* dates;
* section naming;
* section ordering;
* дублирование;
* пропущенные секции.

B. Content Quality

* ясность;
* конкретность;
* избыточная вода;
* повторения;
* weak statements;
* vague wording;
* passive wording;
* чрезмерно общие формулировки;
* отсутствие контекста;
* отсутствие результатов.

C. Experience Quality
Для каждого experience entry определить наличие:

* action;
* responsibility;
* technology;
* scope;
* result;
* metric;
* business impact.

Не требовать metric там, где её объективно нет.

D. Project Quality
Проверять:

* purpose;
* role;
* technology;
* implementation;
* scale;
* outcome;
* relevance to target job.

E. Skills Credibility
Для каждого важного skill определить:

* указан ли skill;
* подтвержден ли experience;
* подтвержден ли project;
* находится ли только в skills section;
* насколько сильно он доказан.

==================================================
4. EVIDENCE ENGINE
==================

Создай механизм связи:

Job Requirement
→ Candidate Skill
→ Candidate Evidence
→ Evidence Strength

Пример:

Requirement:
"PostgreSQL experience"

Evidence:
Experience #2 → PostgreSQL → production backend

Evidence strength:
HIGH

Другой пример:

Requirement:
"Power BI"

Resume:
Skills → Power BI

Experience:
No evidence

Evidence strength:
LOW

Система должна различать:

* explicitly supported;
* indirectly supported;
* weakly supported;
* unsupported;
* missing.

Это должно использоваться как в matching, так и в resume optimization.

Не ограничиваться keyword matching.

==================================================
5. ATS ANALYZER
===============

Создай отдельный deterministic ATS analyzer.

Не использовать LLM для базовых ATS-проверок, если проверку можно сделать алгоритмически.

Проверять:

* machine readability;
* стандартные section names;
* contact information;
* dates;
* employment history;
* education;
* skills;
* keyword presence;
* keyword placement;
* duplicate keywords;
* unusual formatting;
* tables;
* multi-column layout;
* headers/footers;
* unsupported symbols;
* suspicious formatting;
* missing information;
* inconsistent dates;
* malformed sections.

ATS результат должен быть explainable.

НЕ делать:

"ATS score = 83"

без объяснения.

Должен быть:

ATS score: 83

Critical:
...
Warnings:
...
Passed:
...

Каждый score должен иметь breakdown.

==================================================
6. JOB REQUIREMENT ENGINE
=========================

Используй существующий Job Intelligence / Matching pipeline.

Из вакансии извлекать:

* required skills;
* preferred skills;
* technologies;
* experience requirements;
* education;
* language;
* responsibilities;
* domain knowledge;
* seniority;
* location;
* employment type;
* salary, если доступна;
* implicit requirements;
* equivalent skills.

Разделять:

HARD REQUIREMENTS
SOFT/PREFERRED REQUIREMENTS
RESPONSIBILITIES
NICE-TO-HAVE
IMPLICIT REQUIREMENTS

Не считать простое совпадение слова полноценным соответствием.

==================================================
7. RESUME ↔ JOB GAP ANALYSIS
============================

Создать полноценный gap analysis:

Requirement
→ importance
→ candidate evidence
→ evidence strength
→ gap
→ recommendation

Например:

SQL
✓ Strong evidence

Power BI
✓ Skill exists
⚠ Weak evidence

DAX
✗ Missing

Stakeholder communication
⚠ Indirect evidence

Рекомендации должны быть actionable.

Не писать:

"Improve your Power BI skills."

Если проблема именно в резюме:

"Power BI указан в Skills, но отсутствует в Experience. Если инструмент действительно использовался в проекте X, добавь его в соответствующий bullet."

==================================================
8. RESUME QUALITY SCORING
=========================

Добавить отдельную оценку качества резюме.

Score должен состоять из explainable components:

* ATS readiness;
* job relevance;
* requirement coverage;
* evidence coverage;
* skill credibility;
* experience quality;
* project relevance;
* clarity;
* impact;
* positioning.

Не смешивать Resume Quality и Job Match Score.

Например:

Resume Quality = насколько хорошо составлено резюме.

Job Match = насколько кандидат подходит конкретной вакансии.

Это разные метрики.

==================================================
9. BULLET ANALYZER
==================

Каждый bullet point анализировать.

Определять:

* action;
* object;
* technology;
* context;
* scope;
* result;
* metric;
* business impact.

Определять weak bullets.

Например:

"Работал с PostgreSQL."

→ weak

Предлагать улучшенную формулировку только на основе известных фактов.

Если фактов недостаточно:

"Недостаточно данных для безопасного улучшения. Укажите, что именно было реализовано."

Не выдумывать результат.

==================================================
10. CONTROLLED AI REWRITING
===========================

LLM должен получать:

* candidate facts;
* current resume;
* target job;
* extracted requirements;
* market benchmark;
* detected issues;
* evidence map.

LLM должен оптимизировать:

* wording;
* ordering;
* relevance;
* keyword placement;
* clarity;
* impact;
* conciseness.

Но не факты.

После генерации обязательно запускать validation pipeline:

Generated Resume
→ Fact Extraction
→ Compare with Candidate Facts
→ Unsupported Claims Detection
→ Reject / Flag

Финальный документ нельзя считать valid, если содержит неподтвержденные факты.

==================================================
11. MARKET INTELLIGENCE
=======================

Это ключевое отличие AutoHH от обычного Resume Builder.

Используй существующий поток вакансий.

На основе накопленных вакансий строить статистику:

* skill frequency;
* technology frequency;
* title frequency;
* seniority;
* salary;
* requirements;
* preferred skills;
* common keywords.

Строить benchmark по ролям.

Например:

Data Analyst Kazakhstan:

SQL — X%
Excel — X%
Power BI — X%
Python — X%

Не захардкодить значения.

Данные должны рассчитываться из реально имеющихся вакансий.

Если sample size слишком маленький — явно показывать это пользователю.

==================================================
12. MARKET-AWARE RESUME OPTIMIZATION
====================================

При оптимизации учитывать:

1. конкретную вакансию;
2. типичные требования рынка;
3. профиль кандидата;
4. доказательность навыков.

Не оптимизировать резюме только под keyword stuffing.

Цель:

maximize relevance
+
maximize evidence
+
maximize readability
+
maximize factual correctness

==================================================
13. APPLICATION FEEDBACK LOOP
=============================

Используй существующий Application Tracking.

Связать:

Resume Version
→ Job
→ Application
→ Response
→ Interview
→ Offer

Система должна позволять анализировать conversion:

applications
→ responses
→ interviews
→ offers

Для разных resume versions.

Например:

Resume A:
100 applications
8 responses
3 interviews

Resume B:
100 applications
14 responses
6 interviews

Не делать вывод о причинности без достаточного количества данных.

Показывать sample size.

==================================================
14. RESUME VERSIONING
=====================

Система должна поддерживать:

Master Resume
+
Job-specific Resume Versions

Каждая версия должна хранить:

* source resume;
* target job;
* changes;
* reason for changes;
* timestamp;
* resulting score;
* ATS score;
* match score;
* evidence coverage;
* application outcome.

Нельзя изменять master resume автоматически при tailoring.

==================================================
15. FRONTEND
============

Не ограничиваться backend.

Добавить полноценный UI.

Основные экраны:

Resume Dashboard

Показывать:

Resume Quality
ATS Readiness
Evidence Coverage
Market Fit
Top Problems
Top Recommendations

Resume Analysis

Показывать:

* Critical issues;
* warnings;
* strengths;
* weak sections;
* unsupported claims;
* missing evidence;
* recommendations.

Job Match

Показывать:

* overall match;
* hard requirements;
* preferred requirements;
* evidence;
* gaps;
* risks.

Resume Optimization

Показывать:

BEFORE
AFTER
WHY

Для каждого изменения.

Пользователь должен иметь возможность:

* accept;
* reject;
* edit.

==================================================
16. EXPLAINABILITY
==================

Каждая рекомендация должна иметь reason.

Плохо:

"Improve your resume."

Хорошо:

"Power BI is required by 7 of 10 target jobs and appears only in your Skills section. Move it into Experience if supported by your actual work."

Каждый score должен быть explainable.

==================================================
17. ARCHITECTURE
================

Не создавать монолитный ResumeAnalyzerService на тысячи строк.

Разделить ответственность.

Предпочтительная структура:

ResumeAnalysisService
ATSAnalyzer
ResumeQualityAnalyzer
EvidenceAnalyzer
BulletAnalyzer
ResumeOptimizationService
ResumeValidationService
JobRequirementService
MarketBenchmarkService

Но сначала проверь существующую архитектуру.

Если существующий service уже решает соответствующую задачу, расширь его вместо создания дубликата.

Не создавать параллельные реализации одной бизнес-логики.

==================================================
18. DETERMINISTIC VS LLM
========================

Обязательное правило:

Deterministic:

* calculations;
* scoring;
* dates;
* experience;
* ATS structural checks;
* fact validation;
* keyword statistics;
* market statistics;
* thresholds.

LLM:

* semantic interpretation;
* requirement extraction;
* wording analysis;
* bullet rewriting;
* qualitative explanation.

Не использовать LLM там, где deterministic implementation надежнее, дешевле и тестируемее.

==================================================
19. PERFORMANCE
===============

Не запускать несколько дорогих LLM requests без необходимости.

Использовать:

* caching;
* normalized job representation;
* normalized resume representation;
* reusable embeddings;
* batch processing;
* deterministic preprocessing.

Одинаковый resume/job не должен повторно анализироваться без необходимости.

==================================================
20. DATABASE
============

Перед изменением schema изучи существующие models.

Не дублировать уже существующие сущности.

Если нужны новые сущности, предусмотреть минимум:

ResumeAnalysis
ResumeIssue
ResumeRecommendation
Evidence
ResumeVersion
MarketBenchmark

Но конкретную schema определить после аудита текущих моделей.

Все изменения должны иметь migrations.

==================================================
21. API
=======

API должно быть REST-consistent и соответствовать существующему стилю проекта.

Добавить endpoints только после изучения существующих routes.

Не создавать дублирующиеся endpoints.

Все endpoints должны иметь:

* validation;
* authentication/authorization;
* proper error handling;
* predictable response schema.

==================================================
22. TESTING
===========

Добавить tests.

Минимум:

Unit tests:

* ATS analyzer;
* scoring;
* evidence classification;
* gap analysis;
* hallucination detection;
* bullet analysis;
* market statistics.

Integration tests:

* resume → analysis;
* job → requirements;
* resume + job → optimization;
* generated resume → validation.

Regression tests:
существующий matching не должен сломаться.

Создай fixtures с реальными edge cases:

* пустое резюме;
* неполное резюме;
* очень длинное резюме;
* duplicate skills;
* missing dates;
* unusual formatting;
* unsupported LLM claim;
* skill only in Skills;
* skill supported by experience;
* conflicting experience dates.

==================================================
23. SECURITY
============

Проверить:

* authentication;
* authorization;
* user isolation;
* prompt injection из Job Description;
* prompt injection из Resume;
* unsafe generated content;
* sensitive data exposure;
* logging sensitive information;
* LLM input sanitization.

Job Description и Resume являются UNTRUSTED INPUT.

Нельзя позволять содержимому вакансии или резюме менять system instructions.

==================================================
24. OBSERVABILITY
=================

Добавить structured logging там, где это соответствует существующей архитектуре.

Отслеживать:

* analysis duration;
* LLM latency;
* LLM errors;
* cache hits;
* validation failures;
* optimization failures.

Не логировать секреты и чувствительные данные без необходимости.

==================================================
25. UX PRINCIPLE
================

Пользователь должен понимать:

1. Что плохо?
2. Почему это плохо?
3. Насколько это важно?
4. Что именно изменить?
5. Можно ли это изменить без добавления новых фактов?
6. Как изменение повлияет на конкретную вакансию?

Не превращать интерфейс в бессмысленный набор scores.

==================================================
26. НЕ ДЕЛАТЬ
=============

Не делать:

* fake ATS score;
* keyword stuffing;
* hallucinated achievements;
* выдуманные metrics;
* выдуманные skills;
* огромные LLM prompts в каждом endpoint;
* duplicate services;
* duplicate business logic;
* hardcoded market statistics;
* hardcoded job requirements;
* breaking changes без необходимости;
* переписывание существующей архитектуры без причины;
* временные костыли вместо нормальной архитектуры.

==================================================
27. DEFINITION OF DONE
======================

Функциональность считается завершенной только если:

[ ] существующий проект продолжает запускаться;
[ ] существующий matching продолжает работать;
[ ] существующий application tracking продолжает работать;
[ ] resume parsing работает;
[ ] Resume Intelligence работает;
[ ] ATS analysis работает;
[ ] Evidence Engine работает;
[ ] Job Requirement Engine работает;
[ ] Gap Analysis работает;
[ ] Resume Quality Score работает;
[ ] Bullet Analyzer работает;
[ ] Controlled AI Rewriting работает;
[ ] hallucination validation работает;
[ ] Market Benchmark работает;
[ ] Resume Versioning работает;
[ ] Application Feedback Loop работает;
[ ] frontend поддерживает новые возможности;
[ ] database migrations созданы;
[ ] tests добавлены;
[ ] regression tests проходят;
[ ] lint/type checks проходят;
[ ] security issues проверены;
[ ] performance issues проверены;
[ ] нет дублирования бизнес-логики;
[ ] нет TODO вместо реализации;
[ ] нет mock/fake production data;
[ ] нет hardcoded market statistics;
[ ] нет неподтвержденных фактов в автоматически созданном CV.

==================================================
28. ОБЯЗАТЕЛЬНЫЙ WORKFLOW
=========================

Работай поэтапно.

PHASE 1 — AUDIT

Сначала изучи весь репозиторий.

Особенно:

* backend;
* frontend;
* database models;
* schemas;
* routes;
* services;
* existing tests;
* configuration;
* Docker;
* README.

Найди существующие реализации:

* matching;
* scoring;
* resume parsing;
* resume profile;
* keyword matching;
* gap analysis;
* skill taxonomy;
* validation;
* feedback analytics;
* career analytics;
* application tracking.

Не начинай массовые изменения до завершения аудита.

PHASE 2 — ARCHITECTURE

Составь конкретный implementation plan.

Для каждого изменения укажи:

FILE
CURRENT RESPONSIBILITY
CHANGE
REASON
DEPENDENCIES
TESTS

PHASE 3 — IMPLEMENTATION

Реализуй функциональность небольшими логическими блоками.

После каждого блока:

* run tests;
* run lint;
* run type checks;
* проверить regression.

PHASE 4 — INTEGRATION

Интегрируй backend и frontend.

Проверь полный workflow:

Resume
→ Analyze
→ Select Job
→ Match
→ Gap Analysis
→ Optimize
→ Validate
→ Create Version
→ Apply
→ Track Outcome

PHASE 5 — FINAL AUDIT

После реализации повторно проверь:

CORRECTNESS
SCALABILITY
PERFORMANCE
SECURITY
TESTABILITY
MAINTAINABILITY
UX

Особенно ищи:

* duplicate logic;
* unnecessary LLM calls;
* hallucinations;
* inconsistent scores;
* race conditions;
* N+1 queries;
* unvalidated input;
* authorization bugs;
* broken migrations;
* frontend/backend schema mismatch.

==================================================
29. КРИТИЧЕСКОЕ ПРАВИЛО
=======================

Если во время реализации обнаружишь, что существующее архитектурное решение слабее альтернативы:

НЕ ПОДСТРАИВАЙ НОВУЮ ФУНКЦИЮ ПОД ПЛОХУЮ АРХИТЕКТУРУ.

Сначала объясни проблему и предложи более надежный вариант.

Если изменение безопасно и локально — реализуй его.

Если изменение затрагивает большую часть системы — сначала остановись и покажи architecture proposal.

==================================================
30. ФИНАЛЬНЫЙ РЕЗУЛЬТАТ
=======================

В конце ты должен предоставить:

1. Что было найдено в исходной архитектуре.
2. Что было изменено.
3. Какие новые компоненты добавлены.
4. Какие существующие компоненты переиспользованы.
5. Какие архитектурные проблемы исправлены.
6. Как работает новый Resume Intelligence pipeline.
7. Как работает ATS.
8. Как работает Evidence Engine.
9. Как работает Market Intelligence.
10. Как работает feedback loop.
11. Какие тесты добавлены.
12. Результаты тестов.
13. Какие потенциальные технические долги остались.
14. Какие ограничения всё ещё существуют.

Не заявляй "100% готово", если существуют незавершенные функции, mock implementation, TODO или известные критические проблемы.

Главный критерий качества:

AutoHH должен не просто генерировать красивое резюме.

Он должен использовать реальные данные кандидата, реальные требования вакансии, накопленные данные рынка и реальные результаты откликов для систематической оптимизации вероятности получения интервью — без выдумывания опыта кандидата.
