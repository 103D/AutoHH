# Provider Audit (verification report)

Verification method: (1) code-level review of every provider — endpoint,
authentication, pagination, parsing, timeout, retry, response schema,
required configuration; (2) **live HTTP probes** of each provider's real
`fetch_jobs()` from this environment (2026-09); (3) mocked-HTTP unit tests
(`tests/unit/test_ingestion.py`).

Legend: `WORKING` — live-verified; `PARTIAL` — code correct, blocked by
external factor; `CREDENTIALS_REQUIRED` — needs a registration/key;
`UNAVAILABLE` — source changed, returns no data; `NOT_VERIFIED` — not
probed.

## Summary

| Provider | Status | Live probe result |
|----------|--------|-------------------|
| `manual` | WORKING | n/a (serves source config; unit-tested) |
| `remote_ok` | WORKING | 200, 5 jobs parsed with ids/titles/urls |
| `hh_kz` | CREDENTIALS_REQUIRED | 403 `{"errors":[{"type":"forbidden"}]}` — registered User-Agent needed |
| `hh_remote` | CREDENTIALS_REQUIRED | inherits `hh_kz` (same 403) |
| `superjob` | CREDENTIALS_REQUIRED | requires `X-api-app-id`; without key raises `JobSourceError` (no retry — correct) |
| `habr_career` | UNAVAILABLE | 200 but 0 `application/ld+json` blocks on listing page |
| `zarplata` | UNAVAILABLE | 200; ld+json present but only `BreadcrumbList`/`ItemList` — no `JobPosting` |

## hh_kz / hh_remote — HeadHunterKZProvider / HeadHunterRemoteProvider

- Endpoint: `GET https://api.hh.ru/vacancies` (params: `area` default 40 = KZ,
  `per_page` capped to API max 100, `page`, optional `text`/`experience`/
  `employment`/`schedule`). `hh_remote` forces `schedule=remote`.
- Authentication: **no OAuth key**, but HH requires a *registered* User-Agent
  (`AppName/Version (contact email)`, registered at dev.hh.ru). Configurable
  via source config `user_agent` or `HH_USER_AGENT` setting; a descriptive
  error is logged on `bad_user_agent` responses.
- Pagination: single page per call (`page` filter) — the Celery beat schedule
  re-fetches page 0; deep pagination is intentionally not used.
- Parsing: structured `salary`/`area`/`employment`/`schedule`/`experience`
  fields with snippet fallback; deterministic experience extraction.
- Timeout: 30 s (config `timeout`); retry: provider re-raises `httpx` errors,
  the pipeline classifies 429/5xx/timeout as transient (Celery backoff),
  4xx (incl. this 403) as permanent — correct for an auth problem.
- Response schema: HH vacancy list JSON (`items`), verified in unit tests;
  malformed items are skipped per-item.
- **Live probe: 403 Forbidden** until a registered User-Agent is configured.

## remote_ok — RemoteOkProvider

- Endpoint: `GET https://remoteok.com/api` (public feed, no auth, optional
  `tag` param).
- Pagination: single request; first array element is legal metadata — skipped
  by the `id`/`position` guard; malformed items skipped per-item.
- Parsing: salary min/max, ISO date, HTML-stripped description,
  `work_format="remote"` (RemoteOK does not expose currency/employment).
- Timeout: 30 s (config). Retry: transient classification via pipeline.
- **Live probe: 200, 5 real jobs parsed** → WORKING.

## superjob — SuperJobProvider

- Endpoint: `GET https://api.superjob.ru/2.0/vacancies/` (params: `count`
  ≤ 100, `page`, `keywords[]`, `town`, `catalogues[]`; remote-work rubric 33).
- Authentication: `X-api-app-id` header — **requires a registered client id**
  (source config `api_key`); missing key raises `JobSourceError` before any
  HTTP call (classified permanent → no retry — correct).
- Parsing: tolerant (`candidat.requirements/liability`, timestamp → datetime,
  currency normalization); malformed items skipped per-item. Unit-tested.
- **Live probe: not possible without credentials → CREDENTIALS_REQUIRED.**

## habr_career — HabrCareerProvider (JSON-LD scraper)

- Endpoint: `GET https://career.habr.com/vacancies` (+ `q`, `page`, `remote`,
  `city` params), up to `MAX_PAGES=3`.
- Parsing: schema.org `JobPosting` JSON-LD blocks via shared `jsonld.py`
  helpers (unit-tested with fixtures); no postings → empty list (best-effort),
  so a changed layout never breaks the pipeline.
- **Live probe: 200, 274 KB HTML, but zero `application/ld+json` blocks** —
  the listing no longer embeds JobPosting structured data → UNAVAILABLE.
  Vacancies from this source should come through manual import until the
  scraper is updated (out of scope: no new features).

## zarplata — ZarplataProvider (JSON-LD scraper)

- Endpoint: `GET https://zarplata.ru/vacancies` (+ `text`, `page`, `remote`).
- Same JSON-LD parsing approach and unit coverage as habr_career.
- **Live probe: 200, 1.9 MB page; ld+json blocks exist but contain only
  `BreadcrumbList` and `ItemList` — no `JobPosting`** → UNAVAILABLE. Same
  fallback as habr_career.

## manual — ManualProvider

- No network: serves vacancies embedded in the source configuration; text
  filter; stable generated `external_id`; invalid entries skipped per-item
  (unit-tested). Powers the mandatory manual-import path (normalized/deduped
  exactly like every provider). WORKING.

## Cross-cutting (all HTTP providers)

- Timeout: per-source `timeout` config (default 30 s) — verified in code.
- Retry: providers raise raw `httpx` errors; `SourceFetchPipeline` classifies
  them (`app/providers/jobs/exceptions.py`): 429 → `RateLimitError`, 5xx/
  timeouts/network → `TransientFetchError` (Celery `autoretry_for`, backoff
  ≤ 300 s, max 3), 4xx/auth/config → `PermanentFetchError` (no retry, source
  health records the failure). Malformed JSON body → transient.
- Health: repeated permanent/transient failures increment
  `consecutive_errors` and auto-disable the source after
  `max_consecutive_source_errors` (default 5); a successful fetch (including
  **zero jobs**) resets the counter — an empty response does NOT mark a
  provider broken.
