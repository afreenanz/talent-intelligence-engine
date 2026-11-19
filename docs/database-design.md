# Database Design

> Status: **As built (documentation pass after Milestone 10).** Generated against the live schema
> (`information_schema`, `pg_indexes`, `pg_constraint`) at Alembic head `a68d84800899`, then annotated.
> Where the build differs from the Milestone 0 design, "Changed from design" says what and why.

PostgreSQL 17 with extensions `vector` 0.8.7 (pgvector), `citext` (case-insensitive email) and
`pg_trgm`. **Note:** `pg_trgm` is installed by the init script but not used yet. Near-duplicate
detection compares description shingles in Python (see §3.7), so no trigram index exists.

Two schemas:
- `public`: the application tables below, owned by Alembic (7 migrations, every change reviewed by hand).
- `langgraph`: `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`, owned by
  LangGraph's `PostgresSaver` (the agent's execution state). It's kept apart so the app's migrations and
  LangGraph's own never collide (ADR-009). The migration that creates the agent tables creates and drops
  this schema.

## 1. ER diagram

```mermaid
erDiagram
    users ||--o| candidate_profiles : has
    users ||--o{ refresh_tokens : issues
    candidate_profiles ||--o{ resumes : uploads
    candidate_profiles ||--o{ candidate_skills : has
    candidate_profiles ||--o{ candidate_embeddings : "embedded as"
    skills ||--o{ candidate_skills : ""
    skills ||--o{ skill_aliases : "known as"
    skills ||--o{ job_skills : ""
    jobs ||--o{ job_skills : requires
    jobs ||--o{ job_embeddings : "embedded as"
    jobs |o--o{ jobs : "duplicate_of"
    candidate_profiles ||--o{ search_logs : runs
    search_logs |o--o{ job_interactions : "shown in"
    candidate_profiles ||--o{ job_interactions : performs
    jobs ||--o{ job_interactions : receives
    candidate_profiles ||--o{ saved_jobs : saves
    jobs ||--o{ saved_jobs : ""
    candidate_profiles ||--o{ applications : submits
    jobs ||--o{ applications : ""
    candidate_profiles ||--o{ conversations : has
    conversations ||--o{ messages : contains
    candidate_profiles ||--o{ agent_memory : remembers
    ingestion_runs ||--o{ ingestion_errors : records

    users { uuid id PK; citext email UK; text password_hash; bool is_active; bool is_admin }
    candidate_profiles { uuid id PK; uuid user_id FK,UK; text full_name; numeric experience_years; jsonb education; jsonb projects; text location; bigint preferred_salary_min; bigint preferred_salary_max; char3 salary_currency; enum preferred_job_type; enum preferred_location_type; text profile_summary }
    skills { int id PK; text name; text normalized_name UK; text category; bool is_ambiguous }
    skill_aliases { text alias PK; int skill_id FK }
    candidate_skills { uuid candidate_id PK,FK; int skill_id PK,FK; smallint proficiency; int experience_months; enum source }
    resumes { uuid id PK; uuid candidate_id FK; text file_path; text original_filename; char64 file_sha256; int size_bytes; int page_count; text extracted_text; jsonb parsed_data; enum parsing_status; text parsing_error; text llm_model; int llm_latency_ms; int llm_input_tokens; int llm_output_tokens; timestamptz reviewed_at }
    jobs { uuid id PK; text source; text external_id; text title; text normalized_title; text company; text normalized_company; text description; text location; text city; text country; enum location_type; enum employment_type; bigint salary_min; bigint salary_max; char3 salary_currency; numeric experience_min; numeric experience_max; enum status; uuid duplicate_of_job_id FK; char64 content_hash; text skills_text; tsvector search_vector; timestamptz posted_at; timestamptz expires_at; timestamptz listed_at; timestamptz first_seen_at; timestamptz last_seen_at }
    job_skills { uuid job_id PK,FK; int skill_id PK,FK; enum importance }
    job_embeddings { uuid id PK; uuid job_id FK; text embedding_model; vector embedding; char64 content_hash }
    candidate_embeddings { uuid id PK; uuid candidate_id FK; text embedding_model; vector embedding; char64 content_hash }
    search_logs { uuid id PK; uuid candidate_id FK; text query; jsonb filters; text mode; text ranking; int result_count; int latency_ms }
    job_interactions { bigint id PK; uuid candidate_id FK; uuid job_id FK; enum interaction_type; uuid search_log_id FK; int position }
    saved_jobs { uuid candidate_id PK,FK; uuid job_id PK,FK; timestamptz created_at }
    applications { uuid id PK; uuid candidate_id FK; uuid job_id FK; enum application_status; text notes }
    conversations { uuid id PK; uuid candidate_id FK; text title; timestamptz updated_at }
    messages { uuid id PK; bigint seq UK; uuid conversation_id FK; enum role; text content; jsonb tool_metadata }
    agent_memory { uuid id PK; uuid candidate_id FK; enum memory_type; text memory_key; jsonb memory_value; float confidence; enum source }
    ingestion_runs { uuid id PK; text source; enum mode; text file_name; enum status; int received; int inserted; int updated; int unchanged; int duplicates; int failed; int expired; int removed; text error }
    ingestion_errors { bigint id PK; uuid run_id FK; text source; text external_id; jsonb raw_record; text error_type; text error_message; bool retryable; int attempts; timestamptz resolved_at }
    evaluation_runs { uuid id PK; text experiment_name; text dataset_version; text split; jsonb configuration; jsonb metrics; text git_commit }
```

Most tables also have `created_at` / `updated_at` (`timestamptz`, set by the database; `updated_at` is
refreshed on every ORM or Core update).

## 2. What each group of tables is for

| Tables | Purpose |
|---|---|
| `users`, `refresh_tokens` | Accounts. Only a **hash** of each refresh token is stored, so a database leak gives no usable tokens. Tokens rotate on use; reuse of a rotated token revokes the session. |
| `candidate_profiles`, `candidate_skills`, `candidate_embeddings` | The candidate. Skills are relational because ranking joins and counts them; `source` records `manual` or `resume`. |
| `skills`, `skill_aliases` | One shared vocabulary (138 curated skills + aliases), so "Postgres", "postgresql" and "PostgreSQL" are one skill on both sides of a match. `is_ambiguous` marks words like "Go" or "R" that need context before matching in free text. |
| `resumes` | Upload, extracted text, the raw extraction (`parsed_data`), the review timestamp, and LLM cost/latency per résumé. The raw extraction stays separate from the profile until the user approves it. |
| `jobs`, `job_skills`, `job_embeddings` | Listings, their skills (required / preferred / mentioned) and vectors. |
| `ingestion_runs`, `ingestion_errors` | Every import is auditable; rejected records keep the raw payload and a `retryable` flag, so they can be retried without re-importing the file. |
| `search_logs`, `job_interactions` | What was shown (impressions, with position) and what the user did (click, save, unsave, dismiss, apply). Personalization learns from these. |
| `saved_jobs`, `applications` | Current state the UI reads directly. |
| `conversations`, `messages`, `agent_memory` | The assistant's user-visible history and the stated/learned preferences (see [memory-design.md](memory-design.md)). |
| `evaluation_runs` | Every benchmark run: experiment, dataset version, split, configuration, metrics and git commit. The Evaluation page reads it. |

## 3. Key design decisions

### 3.1 UUIDs for entities, bigint for append-only logs
User-facing entities use UUIDs: safe in URLs, don't reveal row counts, can be generated before insert.
High-volume append-only logs (`job_interactions`, `ingestion_errors`) use `bigint identity`, smaller and
with sequential index inserts. The `skills` vocabulary uses `int`.

### 3.2 Event log vs current state
`job_interactions` is an **immutable event log**; `saved_jobs` and `applications` are **current state**.
The UI asks "is this saved?" (a primary-key lookup); personalization asks "how did behaviour evolve?",
which needs the history, including un-saves. Both are written in one transaction.

### 3.3 Impressions are logged, and never count as negative
A click only means something relative to what was shown. Each search logs one impression per result with
its 1-based `position`. Not clicking a shown job is **not** treated as a dislike; only explicit
"not interested" is negative.

### 3.4 Messages are ordered by `seq`, not `created_at`
**Changed from design.** Messages written in one transaction share the same `now()`, so ordering by
`created_at` returned them in random order (found in Milestone 6A). `messages.seq` is a `bigint`
identity with its own unique index, and `(conversation_id, seq)` is the read index.

### 3.5 JSONB where data is read as a document
`education` and `projects` (validated by Pydantic) are always read and written whole, never filtered on.
`parsed_data`, `filters`, `tool_metadata`, `memory_value`, `configuration` and `metrics` are the same kind
of data. Anything ranking queries (skills) is relational.

### 3.6 Embeddings in their own tables
`(job_id, embedding_model)` is unique, so two models' vectors can coexist during an evaluation without
touching `jobs`. `content_hash` on the embedding row records *what text was embedded*; a job is
re-embedded only when its text hash changes. Vectors are 384-dimensional; a model with another dimension
needs its own column or table (ADR-006).

### 3.7 Full-text search vector as a generated column
```sql
search_vector tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')),       'A')
 || setweight(to_tsvector('english', coalesce(skills_text, '')), 'B')
 || setweight(to_tsvector('english', coalesce(company, '')),     'C')
 || setweight(to_tsvector('english', coalesce(description, '')), 'D')
) STORED
```
The database keeps it in sync. Skills live in another table, so ingestion maintains a denormalised
`skills_text` in the same transaction. **Changed from design:** skills got their own weight (B) above
company and description, because a skill match is a stronger signal than a word in the description.

### 3.8 Deduplication
- **Hard identity:** `UNIQUE (source, external_id)` makes re-importing a file a no-op.
- **Near-duplicates:** candidates share `(normalized_company, normalized_title)` (btree `ix_jobs_dedup_key`)
  and city; then description shingles are compared with Jaccard similarity, and the listings must have been
  live at the same time (a repost after the original expired is a new opening). Duplicates are **kept**
  with `status = 'duplicate'` and `duplicate_of_job_id`, so the decision is auditable and reversible.
- A check constraint enforces `(status = 'duplicate') = (duplicate_of_job_id IS NOT NULL)`.

### 3.9 Salaries
Stored as **annual whole-currency integers** with an ISO-4217 `salary_currency`. "15 LPA" becomes
1,500,000 INR at ingestion. Ranking compares salaries only within one currency; a check constraint
requires a currency whenever a salary is present.

### 3.10 Listing dates
`posted_at` is only what the source said, never invented. `listed_at` (the sort key) is `posted_at` if
known, else first-seen time. `first_seen_at` / `last_seen_at` support snapshot imports, where a job
missing from a full feed is marked `removed`.

## 4. Indexes (as built)

| Index | Purpose |
|---|---|
| `uq_jobs_source_external_id (source, external_id)` | Idempotent upsert |
| `ix_jobs_search_vector` GIN `(search_vector)` | Full-text search. The planner may prefer a seq scan at 1.6k rows; the index is proven usable (performance-benchmarks.md) |
| `ix_jobs_status_listed_at (status, listed_at DESC, id)` | Active-job listing and keyset pagination |
| `ix_jobs_dedup_key (normalized_company, normalized_title)` | Near-duplicate candidates |
| `ix_jobs_active_expires_at (expires_at) WHERE status = 'active' AND expires_at IS NOT NULL` | The hourly expiry sweep touches only active jobs with a date |
| `uq_job_embeddings_job_model (job_id, embedding_model)` | One vector per job per model |
| `ix_job_skills_skill_id`, `ix_candidate_skills_skill_id` | Skill → jobs / candidates lookups |
| `ix_job_interactions_candidate_created`, `ix_job_interactions_job` | Per-candidate history; per-job counts |
| `ix_search_logs_candidate_created` | Recent searches |
| `ix_messages_conversation_seq`, `uq_messages_seq` | Conversation replay in write order |
| `ix_conversations_candidate_updated` | Conversation list, newest first |
| `uq_agent_memory_key (candidate_id, memory_type, memory_key)` | Upsert a preference instead of duplicating it |
| `uq_applications_candidate_job` | One application per job |
| `ix_resumes_candidate_created` | A candidate's uploads, newest first |
| `ix_ingestion_errors_unresolved (run_id) WHERE resolved_at IS NULL` | Retry only what's still failing |
| `ix_evaluation_runs_experiment_created` | Latest runs per experiment |
| `uq_users_email` (citext), `uq_refresh_tokens_token_hash`, `uq_skills_normalized_name` | Identity lookups |

**No vector index.** **Changed from design:** an HNSW index was built, measured and rolled back in
Milestone 7B. At ~1.6k vectors an exact scan takes ~2–3 ms; HNSW saved under 1 ms and lost some recall
(0.985 recall@10). Revisit around 50k vectors or a dense p95 above 50 ms.

## 5. Constraints

Check constraints (all in the live schema):
- `jobs`: `salary_min <= salary_max`; a currency whenever a salary is set; `experience_min <= experience_max`;
  `duplicate_of_job_id <> id`; duplicate status ⇔ duplicate link.
- `candidate_profiles`: `experience_years` between 0 and 60; salary range ordered and non-negative.
- `candidate_skills`: `proficiency` 1–5; `experience_months >= 0`.
- `agent_memory`: `confidence` between 0 and 1.

Foreign keys:
- **CASCADE** from everything a candidate owns (profile, skills, résumés, embeddings, searches,
  interactions, saved jobs, applications, conversations, messages, memory, refresh tokens), so deleting a
  user deletes their data.
- **RESTRICT** from interactions, saved jobs, applications and job skills to `jobs`/`skills`. Jobs are
  expired, never deleted, so history stays intact.
- **SET NULL** from `job_interactions.search_log_id` and `jobs.duplicate_of_job_id`.

## 6. Enums

| Enum | Values |
|---|---|
| `job_status` | `active`, `expired`, `duplicate`, `removed` |
| `resume_status` | `pending`, `processing`, `parsed`, `failed`, `reviewed` |
| `interaction_type` | `impression`, `click`, `save`, `unsave`, `dismiss`, `apply` |
| `application_status` | `applied`, `screening`, `interviewing`, `offer`, `rejected`, `withdrawn` |
| `memory_type` | `explicit_preference`, `derived_preference` |
| `memory_source` | `settings`, `agent`, `derived` |
| `message_role` | `user`, `assistant`, `tool` |
| `location_type` | `onsite`, `remote`, `hybrid` |
| `employment_type` | `full_time`, `part_time`, `contract`, `internship`, `temporary` |
| `skill_importance` | `required`, `preferred`, `mentioned` |
| `skill_source` | `manual`, `resume` |
| `ingestion_mode` | `incremental`, `snapshot` |
| `ingestion_run_status` | `running`, `completed`, `failed` |

**Changed from design:** `memory_type` has no `fact` value: free-form facts can't be validated and the
ranker can't use them, so only the fixed preference vocabulary is stored (memory-design.md). `message_role`
has no `system`: the system prompt is code, not conversation history.

Enums are PostgreSQL `ENUM` types via Alembic. Adding a value needs a migration, which forces a deliberate decision.

## 7. Migrations

| Revision | Adds |
|---|---|
| `f395728ae912` | users, refresh tokens, candidates, skills, aliases |
| `265b9963294b` | jobs, job skills, ingestion runs and errors |
| `f244ee3f984c` | résumés |
| `3dcced24e94a` | search vector (generated), embeddings tables |
| `5340709bcd09` | evaluation runs |
| `dbd166f11fd2` | search logs, interactions, saved jobs, applications, agent memory |
| `a68d84800899` | conversations, messages (`seq`), the `langgraph` schema |

CI runs `alembic check`, which fails if the models and the migrations ever drift apart.
