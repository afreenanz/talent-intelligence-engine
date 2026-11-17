# Database Design

> Status: **Design (Milestone 0)**. The schema is implemented through Alembic migrations
> in Milestones 1–5. Column-level details may change during implementation, and changes are recorded here.

PostgreSQL 17 + pgvector 0.8.x. Extensions: `vector`, `pg_trgm` (fuzzy title/skill
matching for dedup and alias lookup), `citext` (case-insensitive email).

## 1. ER diagram

```mermaid
erDiagram
    users ||--o| candidate_profiles : has
    users ||--o{ refresh_tokens : issues
    candidate_profiles ||--o{ resumes : uploads
    candidate_profiles ||--o{ candidate_skills : has
    skills ||--o{ candidate_skills : ""
    skills ||--o{ skill_aliases : "known as"
    skills ||--o{ job_skills : ""
    jobs ||--o{ job_skills : requires
    jobs ||--o{ job_embeddings : "embedded as"
    jobs |o--o{ jobs : "duplicate_of"
    candidate_profiles ||--o{ candidate_embeddings : "embedded as"
    candidate_profiles ||--o{ job_interactions : performs
    jobs ||--o{ job_interactions : receives
    candidate_profiles ||--o{ saved_jobs : saves
    jobs ||--o{ saved_jobs : ""
    candidate_profiles ||--o{ applications : submits
    jobs ||--o{ applications : ""
    candidate_profiles ||--o{ search_logs : runs
    candidate_profiles ||--o{ conversations : has
    conversations ||--o{ messages : contains
    candidate_profiles ||--o{ agent_memory : remembers
    ingestion_runs ||--o{ ingestion_errors : records
    evaluation_runs

    users { uuid id PK; citext email UK; text password_hash; timestamptz created_at; timestamptz updated_at; bool is_admin }
    candidate_profiles { uuid id PK; uuid user_id FK,UK; text full_name; numeric experience_years; jsonb education; jsonb projects; text location; bigint preferred_salary_min; bigint preferred_salary_max; enum preferred_job_type; text profile_summary }
    skills { int id PK; text name; text normalized_name UK; text category }
    skill_aliases { text alias PK; int skill_id FK }
    candidate_skills { uuid candidate_id PK,FK; int skill_id PK,FK; smallint proficiency; int experience_months; enum source }
    resumes { uuid id PK; uuid candidate_id FK; text file_path; text extracted_text; jsonb parsed_data; enum parsing_status; text parsing_error; timestamptz created_at }
    jobs { uuid id PK; text source; text external_id; text title; text normalized_title; text company; text description; text location; enum location_type; enum employment_type; bigint salary_min; bigint salary_max; char3 salary_currency; numeric experience_min; numeric experience_max; enum status; uuid duplicate_of_job_id FK; char64 content_hash; tsvector search_vector; timestamptz posted_at; timestamptz expires_at }
    job_skills { uuid job_id PK,FK; int skill_id PK,FK; enum importance }
    job_embeddings { uuid id PK; uuid job_id FK; text embedding_model; vector embedding; char64 content_hash; timestamptz created_at }
    candidate_embeddings { uuid id PK; uuid candidate_id FK; text embedding_model; vector embedding; char64 content_hash; timestamptz updated_at }
    job_interactions { bigint id PK; uuid candidate_id FK; uuid job_id FK; enum interaction_type; int position; uuid search_log_id FK; timestamptz created_at }
    saved_jobs { uuid candidate_id PK,FK; uuid job_id PK,FK; timestamptz created_at }
    applications { uuid id PK; uuid candidate_id FK; uuid job_id FK; enum application_status; timestamptz created_at; timestamptz updated_at }
    search_logs { uuid id PK; uuid candidate_id FK; text query; jsonb filters; text pipeline; int result_count; int latency_ms; timestamptz created_at }
    conversations { uuid id PK; uuid candidate_id FK; text title; timestamptz created_at }
    messages { uuid id PK; uuid conversation_id FK; enum role; text content; jsonb tool_metadata; timestamptz created_at }
    agent_memory { uuid id PK; uuid candidate_id FK; enum memory_type; text memory_key; jsonb memory_value; real confidence; enum source; timestamptz updated_at }
    ingestion_runs { uuid id PK; text source; enum status; int inserted; int updated; int unchanged; int duplicates; int failed; timestamptz started_at; timestamptz finished_at }
    ingestion_errors { bigint id PK; uuid run_id FK; jsonb raw_record; text error; int attempts; bool retryable; timestamptz created_at }
    refresh_tokens { uuid id PK; uuid user_id FK; char64 token_hash UK; timestamptz expires_at; timestamptz revoked_at }
    evaluation_runs { uuid id PK; text experiment_name; text dataset_version; jsonb configuration; jsonb metrics; text git_commit; timestamptz created_at }
```

## 2. Tables beyond the required minimum, and why

> Milestone 5A (implemented): `search_logs`, `job_interactions` (impressions are logged
> server-side with 1-based positions), `saved_jobs`, `applications` (plus `notes`, and a status
> state machine with terminal states rejected/withdrawn), `agent_memory` (plus `source`,
> `created_at`). Migration `dbd166f11fd2`.

> Changes made during Milestone 2A (implemented): `jobs` gained `city`, `country`, `normalized_company`,
> `listed_at` (sort key = `posted_at` if the source gave one, else first-seen time, so `posted_at`
> is never invented), `first_seen_at`, `last_seen_at` (needed for snapshot mode). `job_skills.importance`
> gained `mentioned` (found in text, importance unknown). `skills.is_ambiguous` was added. See [ingestion.md](ingestion.md).

| Table | Why it exists |
|---|---|
| `skill_aliases` | "Postgres", "postgresql" and "PostgreSQL" must map to one `skills` row, or skill-overlap features are wrong. Lookup is an exact match on a lowercased alias, with `pg_trgm` fuzzy fallback for suggestions. |
| `refresh_tokens` | Short-lived access JWTs (15 min) plus revocable refresh tokens. Only the **hash** is stored, so a DB leak doesn't leak usable tokens. |
| `search_logs` | Powers "recent searches", links interactions to the result list they came from (`position`, needed for position-bias handling), and provides latency data for benchmarks. |
| `ingestion_runs` / `ingestion_errors` | Each import is auditable (inserted/updated/unchanged/duplicate/failed counts). Failed records are stored with the raw payload so they can be retried without re-importing the whole file. |

## 3. Key design decisions

### 3.1 UUID primary keys for entities, bigint for append-only event logs
User-facing entities use UUIDs, which are safe to expose in URLs, don't reveal row counts,
and can be generated in the app before insert. High-volume append-only logs
(`job_interactions`, `ingestion_errors`) use `bigint identity`, which is smaller and makes
index inserts sequential. The `skills` vocabulary uses `int`.

### 3.2 Event log vs. current-state tables
`job_interactions` is an **immutable event log**: impression, click, save, unsave,
dismiss, apply. `saved_jobs` and `applications` are **current state**. Both are needed:
- The UI asks "is this job saved?", which is a primary-key lookup on `saved_jobs`.
- Personalization asks "how did behaviour evolve?", which needs the full history, including un-saves.

Writing both happens in a single transaction in the service layer.

### 3.3 Impressions are logged
A click only means something relative to what was shown. Logging impressions with
`position` makes it possible to estimate click-through rate by position and avoid treating
"didn't click item #9" as negative feedback. This is the minimum needed to handle
"a click is not always a positive preference" honestly.

### 3.4 JSONB where data is read as a document, relational where it is queried
- `education` and `projects` on the profile are JSONB, validated by Pydantic. They are
  always read and written as a whole and never joined or filtered on.
- Skills are relational (`candidate_skills`, `job_skills`) because ranking joins and
  counts them.
- `resumes.parsed_data` keeps the raw LLM extraction output separate from the
  user-approved profile. The user reviews it before anything is copied into
  `candidate_profiles` / `candidate_skills`. `candidate_skills.source` records `resume` or `manual`.

### 3.5 Embeddings in separate tables
- `job_embeddings(job_id, embedding_model)` is unique. Changing or A/B-testing an
  embedding model doesn't require touching `jobs`, and both models' vectors can coexist
  during an evaluation.
- `content_hash` on the embedding row records **what text was embedded**. An embedding
  is regenerated only when `jobs.content_hash ≠ job_embeddings.content_hash`. This is
  how "avoid generating embeddings unnecessarily" is enforced.
- Constraint: a pgvector column has a fixed dimension. The baseline models are 384-d. A
  model with a different dimension needs its own column or table, which is a deliberate limitation, documented in ADR-006.

### 3.6 Full-text search vector as a generated column
```sql
search_vector tsvector GENERATED ALWAYS AS (
  setweight(to_tsvector('english', coalesce(title,'')),   'A') ||
  setweight(to_tsvector('english', coalesce(company,'')), 'B') ||
  setweight(to_tsvector('english', coalesce(description,'')), 'C')
) STORED
```
The database keeps it in sync, so no trigger or app code can forget to update it.
Skills (from `job_skills`) can't be in a generated column because they live in another
table, so a denormalized `skills_text` column on `jobs` is maintained by the ingestion
service in the same transaction and included at weight `B`.

### 3.7 Deduplication fields
- Hard identity: `UNIQUE (source, external_id)`, which makes ingestion idempotent.
- Soft identity: `normalized_title` + `company` are checked first using a btree/trigram
  index, then description similarity. Duplicates are **kept** with
  `status='duplicate'` and `duplicate_of_job_id` set rather than deleted, so the
  decision is auditable and reversible.

### 3.8 Salary normalization
Salaries are stored as **annual amounts as integers in whole currency units** with
`salary_currency` (ISO-4217). LPA (lakhs per annum) input is converted at ingestion
(15 LPA becomes 1,500,000 INR). Ranking only compares salaries within the same currency.
Cross-currency comparison is out of scope and documented as such.

## 4. Index plan

| Index | Purpose |
|---|---|
| `jobs (source, external_id)` unique | Idempotent upsert |
| `jobs USING gin (search_vector)` | Full-text search |
| `jobs (status, posted_at DESC)` | Active-job listing + keyset pagination |
| `jobs USING gin (normalized_title gin_trgm_ops)` | Near-duplicate candidate lookup |
| `job_embeddings USING hnsw (embedding vector_cosine_ops)` | ANN search. Added only once the corpus is large enough that exact scan is measurably slow; both are benchmarked. |
| `job_embeddings (job_id, embedding_model)` unique | One vector per job per model |
| `job_interactions (candidate_id, created_at DESC)` | Per-candidate history |
| `messages (conversation_id, created_at)` | Conversation replay |
| `agent_memory (candidate_id, memory_type, memory_key)` unique | Upsert a preference instead of duplicating it |
| `applications (candidate_id, job_id)` unique | One application per job |

**Filtered vector search caveat (from pgvector docs):** HNSW filters *after* the index
scan, so `WHERE status='active' AND location=...` can return fewer than K rows. We use
`hnsw.iterative_scan = relaxed_order` (pgvector ≥ 0.8) and verify the returned count in
tests. The alternative of exact scan with filters first is benchmarked against it.

## 5. Constraints (examples)

- `CHECK (salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max)`
- `CHECK (experience_min IS NULL OR experience_min >= 0)`
- `CHECK (confidence BETWEEN 0 AND 1)` on `agent_memory`
- `CHECK (proficiency BETWEEN 1 AND 5)` on `candidate_skills`
- All FKs to candidate-owned data use `ON DELETE CASCADE`, so deleting a user deletes
  their data. FKs from interactions to `jobs` use `ON DELETE RESTRICT`. Jobs are expired, not deleted.

## 6. Status enums

| Enum | Values |
|---|---|
| `job_status` | `active`, `expired`, `duplicate`, `removed` |
| `parsing_status` | `pending`, `processing`, `parsed`, `failed`, `reviewed` |
| `interaction_type` | `impression`, `click`, `save`, `unsave`, `dismiss`, `apply` |
| `application_status` | `applied`, `screening`, `interviewing`, `offer`, `rejected`, `withdrawn` |
| `memory_type` | `explicit_preference`, `derived_preference`, `fact` |
| `message_role` | `user`, `assistant`, `tool`, `system` |

Enums are implemented as PostgreSQL `ENUM` types via Alembic. Adding a value needs a
migration, which is intended because it forces a deliberate decision.
