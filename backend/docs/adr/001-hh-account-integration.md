# ADR-001: HeadHunter account integration as a separate bounded context

- Status: Proposed
- Date: 2026-09-06

## Context

`app/providers/jobs/hh_kz.py` and `hh_remote.py` collect public vacancies and
produce `RawJob` objects for ingestion. They do not represent an authenticated
applicant and must not store OAuth credentials or perform user actions.

HeadHunter applicant operations require OAuth 2.0 user authorization. Tokens
are sent as `Authorization: Bearer ...`; `/me` is the identity/token check.
Applicant responses are negotiation entities connecting one vacancy and one
resume, with messages and applicant-visible states. Active responses are read
through `GET /negotiations?status=active`; the exact available operations and
states must be treated as remote API data rather than hardcoded workflow rules.

## Decision

Create a separate `app/integrations/hh/` bounded context. Do not extend
`JobSourceProvider` with account methods.

```text
HH OAuth callback
  -> HHAccountService
  -> encrypted HHCredential
  -> HHApplicantClient
       |- get_current_user (/me)
       |- list_resumes
       |- get_resume
       |- apply_to_vacancy
       |- list_negotiations
       |- get_negotiation
       `- sync_messages_and_state
```

### Proposed components

| File | Responsibility |
|---|---|
| `integrations/hh/oauth.py` | PKCE/state generation, code exchange, refresh, revoke |
| `integrations/hh/client.py` | Typed HTTP client, retries, HH errors, User-Agent |
| `integrations/hh/accounts.py` | Account connection lifecycle and `/me` verification |
| `integrations/hh/resumes.py` | Applicant resume synchronization |
| `integrations/hh/negotiations.py` | Apply, negotiations, messages, remote state sync |
| `models/hh.py` | HHAccount, encrypted credential, remote resume/application links |
| `api/v1/hh.py` | Connect/callback/status/disconnect and explicit user actions |
| `workers/tasks/sync_hh.py` | Idempotent background synchronization |

### Data model proposal

`hh_accounts`

- `id`, `user_id`, `hh_user_id`, `host`, `status`;
- encrypted `access_token`, encrypted `refresh_token`;
- `access_token_expires_at`, `scopes`, `last_verified_at`, `last_sync_at`;
- unique `(user_id, host)` and `(hh_user_id, host)` where appropriate.

`hh_resumes`

- `hh_account_id`, `remote_resume_id`, title/status/updated timestamps;
- `raw_data`, `content_hash`, optional link to local `resume_profile_id`;
- unique `(hh_account_id, remote_resume_id)`.

`hh_negotiations`

- `hh_account_id`, `remote_negotiation_id`, `remote_resume_id`,
  `remote_vacancy_id`, applicant state, messages metadata, `raw_data`;
- optional links to local `job_id` and `application_id`;
- unique `(hh_account_id, remote_negotiation_id)`.

### Security rules

- Never store plaintext tokens in logs, errors, Celery payloads or frontend.
- Encrypt credentials at rest with a dedicated key distinct from `SECRET_KEY`.
- OAuth callback must verify one-time, expiring `state` bound to the local user.
- Use PKCE S256 where supported by the registered HH application.
- Refresh under a per-account lock to prevent concurrent token rotation races.
- A failed refresh moves the account to `REAUTH_REQUIRED`; it does not retry
  indefinitely.
- All account/resume/application queries must be scoped by authenticated user.
- Applying is an explicit user action and must use an idempotency guard for the
  `(account, remote_resume, remote_vacancy)` tuple.

### Error semantics

- timeout/429/5xx: transient retry with bounded backoff;
- invalid/expired access token: refresh once, then retry once;
- invalid refresh token or revoked grant: `REAUTH_REQUIRED`, no background loop;
- permission/business-rule errors: permanent result visible to the user;
- malformed remote item: quarantine/skip item, continue sync batch.

## Consequences

- Public vacancy ingestion stays simple and credential-free.
- User identity and actions receive a dedicated security boundary.
- Local `Application` remains the product workflow; HH negotiation state is a
  linked remote fact, not a replacement enum.
- This change requires authentication/user isolation before production rollout.

## Delivery milestones

1. Authentication/ownership boundary and encrypted credential primitive.
2. OAuth connect/callback/disconnect plus `/me` verification.
3. Read-only resume and negotiation synchronization.
4. Link remote entities to local Job/Application/ResumeProfile.
5. Explicit apply action with idempotency and audit event.
6. Status/message sync workers, observability and recovery tests.

No milestone should mix HH applicant operations into job-source ingestion.