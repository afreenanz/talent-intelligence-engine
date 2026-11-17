# API reference

Generated from the application's OpenAPI schema. Interactive docs: `http://localhost:8080/docs` (Swagger UI) and `/redoc`.

**Conventions**
- Base path `/api/v1` (health checks are unversioned). JSON in and out.
- Auth: `Authorization: Bearer <access_token>` from `POST /api/v1/auth/login` on every endpoint except register, login, refresh and health. Evaluation endpoints additionally require an admin user (`python -m app.cli make-admin <email>`).
- Errors always use one envelope: `{"error": {"code", "message", "details", "request_id"}}`. Codes: `validation_error` (422), `unauthenticated` (401), `forbidden` (403), `not_found` (404), `conflict` / `job_unavailable` (409), `payload_too_large` (413), `unsupported_media_type` (415), `upstream_unavailable` (503), `internal_error` (500).
- Every response carries `X-Request-ID` (pass your own to correlate logs).
- Lists use opaque `next_cursor` keyset pagination where they can grow (jobs, saved jobs).

## health

| Method | Path | Description |
|---|---|---|
| GET | `/health/live` | Live |
| GET | `/health/ready` | Ready |

## auth

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Register |
| POST | `/api/v1/auth/login` | Login |
| POST | `/api/v1/auth/refresh` | Refresh |
| POST | `/api/v1/auth/logout` | Logout |

## candidates

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/candidates/me` | Get Me |
| PUT | `/api/v1/candidates/me` | Update Me |
| GET | `/api/v1/candidates/me/searches` | Recent Searches |

## resumes

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/candidates/resume` | Upload Resume |
| GET | `/api/v1/candidates/resumes` | List Resumes |
| GET | `/api/v1/candidates/resumes/{resume_id}` | Get Resume |
| DELETE | `/api/v1/candidates/resumes/{resume_id}` | Delete Resume |
| POST | `/api/v1/candidates/resumes/{resume_id}/reprocess` | Reprocess Resume |
| POST | `/api/v1/candidates/resumes/{resume_id}/apply` | Apply Resume |

## jobs

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/jobs` | List Jobs |
| GET | `/api/v1/jobs/{job_id}` | Get Job |

## search

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/jobs/search` | Retrieve (lexical / dense / hybrid), then rank. When you search with a query, your profile |
| GET | `/api/v1/recommendations` | Jobs for you, from your profile alone. Personalisation from your activity is Milestone 5. |

## recommendations

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/recommendations/feedback` | Record a click or a dismissal ("not interested"). |

## saved-jobs

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/saved-jobs` | Save |
| GET | `/api/v1/saved-jobs` | List Saved |
| DELETE | `/api/v1/saved-jobs/{job_id}` | Unsave |

## applications

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/applications` | List Applications |
| POST | `/api/v1/applications` | Apply |
| PATCH | `/api/v1/applications/{application_id}` | Update Application |

## preferences

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/candidates/me/preferences` | Everything stored about your preferences: what you stated and (later) what was inferred. |
| PUT | `/api/v1/candidates/me/preferences/{key}` | Set Preference |
| DELETE | `/api/v1/candidates/me/preferences/{key}` | Delete Preference |

## agent

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/agent/chat` | Send a message. If the assistant wants to save a job or change a preference, the response |
| POST | `/api/v1/agent/conversations/{conversation_id}/confirm` | Confirm |
| GET | `/api/v1/agent/conversations` | Conversations |
| GET | `/api/v1/agent/conversations/{conversation_id}` | Conversation |
| DELETE | `/api/v1/agent/conversations/{conversation_id}` | Delete |

## evaluations

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/evaluations` | List Runs |
| GET | `/api/v1/evaluations/{run_id}` | Get Run |
| POST | `/api/v1/evaluations/run` | Start Run |

