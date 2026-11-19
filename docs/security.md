# Security

> Status: **Audited in Milestone 10 (2026-11-19).** Scope: the code in this repository and the Docker
> stack as shipped. Not a penetration test.

## What we protect, from whom

| Asset | Threat |
|---|---|
| Candidate data (profile, résumé PDFs, saved jobs, conversations) | Another user reading or changing it; a stranger on a shared link |
| Accounts | Password guessing, stolen tokens |
| The owner's Gemini quota | Strangers on a shared link driving the assistant or résumé parsing |
| The machine running it | The database or Redis being reachable from the local network |

## Controls

| Area | Control | Where |
|---|---|---|
| Passwords | Argon2id; minimum 10 characters; login never reveals whether an email exists | `core/security.py`, `domains/auth` |
| Tokens | 15-min JWT access token (HS256, algorithm pinned on decode, issuer checked); 14-day refresh tokens stored hashed, rotated on every use, reuse revokes the session; production refuses a default/short secret | `core/security.py`, `core/config.py` |
| Ownership | Every owned query filters by the identity from the token; ids in the URL are never trusted alone; tested for saved jobs, applications, résumés and conversations | `domains/*/service.py`, `tests/api` |
| Assistant | Identity comes from auth, never from the model; arguments validated with Pydantic; saves and preference changes need explicit user confirmation; replies checked against tool output | `domains/agent` |
| Prompt injection (résumés) | Skills not present in the PDF text are dropped; dictionary-only matches are unticked suggestions; the user reviews everything before it is saved. Measured in the extraction benchmark (planted injection) | `domains/resumes/postprocess.py` |
| Uploads | PDF signature check, 5 MB / 10-page limit, server-generated path (the filename is display-only), files `0600` in a `0700` folder; deleting a résumé deletes the file | `domains/resumes/service.py` |
| SQL | SQLAlchemy expressions throughout; no SQL built from strings (checked by search) | |
| XSS | React escaping; assistant replies rendered as elements, never HTML (tested with an `<img onerror>` payload); CSP `script-src 'self'` + one hash | `features/assistant/Reply.tsx`, `infra/nginx` |
| Abuse | Rate limits (Redis): sign-up 10/h and sign-in 20/15 min per address; assistant 40/h, résumé 10/h, search 120/min per user; `SIGNUP_ENABLED=false` for public demos | `core/rate_limit.py` |
| Client address | nginx overwrites `X-Forwarded-For` (no spoofing); behind the tunnel uses `CF-Connecting-IP`, trusted only from private addresses | `infra/nginx/default.conf` |
| Network | All published ports bound to `127.0.0.1`; the API, worker and database are reachable only inside Docker | `docker-compose.yml` |
| Containers | Non-root user (uid 10001); models baked in, `HF_HUB_OFFLINE=1` | `backend/Dockerfile` |
| Secrets | Only in `.env` (git-ignored); `.env.example` has no values | |
| Errors and logs | Generic 500s with a request ID; no passwords or tokens logged | `core/errors.py` |

## Audit results (Milestone 10)

| Check | Result |
|---|---|
| Git history for committed secrets (`.env`, keys, Google/OpenAI/GitHub token patterns, generated passwords) | None found |
| Python dependencies (`pip-audit` on the locked set) | 1 finding: `dnspython` 2.9.1, CVE-2026-128089. Only reached through email validation, which does no DNS lookups here. **Fixed** anyway: upgraded to 2.9.2 (only that package; the release cutoff moved 2 days) → 0 findings |
| npm production dependencies (`npm audit`) | 4 moderate, one root cause: `minimatch` ReDoS via `ts-morph`, pulled in by the `shadcn` CLI. **Accepted:** it runs only on a developer's machine when adding components, never in the browser bundle; the offered fix is a major downgrade |
| Ownership on every `{id}` route | Scoped and tested |
| JWT verification | Algorithm pinned, signature and issuer verified |
| Upload handling | Signature, size and path checks present; file removed on delete |
| Rate-limit bypass | Found in 9A (client-chosen `X-Forwarded-For`), fixed and re-tested |
| Network exposure | Found in 9B (Postgres and Redis on all interfaces), fixed |

## Accepted risks

- **Refresh token in `localStorage`.** Readable by an XSS bug, unlike an `httpOnly` cookie. Mitigated by
  the strict CSP, React escaping, short access tokens and refresh rotation with reuse detection
  (ADR-013). Moving to a cookie needs CSRF protection too.
- **Sign-up reveals that an email exists** (409). Needed for a usable sign-up form; rate-limited.
- **Free-tier Gemini** may use prompts to improve Google's models. The UI says so where text is sent
  (assistant, résumé), and the docs tell users to upload only their own or fictional résumés.
- **Rate limiter fails open** if Redis is down (availability over strictness, ADR-014).

## Known gaps (not built)

- No account deletion or data export endpoint. A real deployment would need both (right to erasure).
- No email verification or password reset (there is no email sending).
- No audit log of admin actions.
- Quick tunnels are meant for testing: no uptime guarantee, and anyone with the link can open the site.
