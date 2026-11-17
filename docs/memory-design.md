# Memory Design

> Status: **Explicit preferences implemented (Milestone 5A)**: `agent_memory` table, fixed validated
> vocabulary (`app/domains/preferences/schemas.py`), `GET/PUT/DELETE /api/v1/candidates/me/preferences`.
> Every write returns the previous value. **Derived preferences implemented (5B)**: rebuilt from the event
> log after each save/unsave/apply/feedback (rules in ranking-engine.md, Personalization). Agent writes are Milestone 6.
> See ADR-009.

Implemented vocabulary: `role_categories {prefer, avoid}` (backend, frontend, fullstack, data, ml,
devops, mobile, qa, security, design, product; a category can't be both), `locations {cities}`,
`location_type {value}`, `min_salary {amount, currency}`, `employment_type {value}`,
`company_avoid {companies}`, `skills_to_use {skills}`. An invalid value returns 422 with field details.

## Three kinds of memory, three stores

| Kind | Store | Lifetime | Who writes | Editable by user |
|---|---|---|---|---|
| Conversation history | `messages` | per conversation | agent `persist` node | delete conversation |
| Graph execution state | LangGraph `PostgresSaver` tables | per thread; prunable | LangGraph | no (internal) |
| Explicit preferences | `agent_memory` (`explicit_preference`) | until changed | agent tool (after confirmation) or settings page | **yes** |
| Derived preferences | `agent_memory` (`derived_preference`) | recomputed nightly | Celery job from `job_interactions` | can dismiss/override |
| Profile facts | `candidate_profiles`, `candidate_skills` | until changed | resume review, settings | **yes** |

## Memory update rules
1. **Nothing is stored as long-term memory just because it was said.** Only a confirmed `update_candidate_preferences` tool call writes explicit memory.
2. Keys come from a fixed vocabulary validated by Pydantic: `role_category`, `locations`, `location_type`, `salary_min`, `employment_type`, `company_avoid`, `skills_to_use`. Free-text "facts" are not stored in v1 because they can't be validated or used by the ranker.
3. Upsert on `(candidate_id, memory_type, memory_key)`. The new value replaces the old one, and the previous value is returned so the agent can say "changed from X to Y".
4. **Conflicts:** an explicit preference always overrides a derived one for the same key. A request contradicting an existing explicit preference triggers a confirmation that names the conflict.
5. Derived preferences require minimum support and carry a confidence below 1. They are never shown to the LLM as facts ("you prefer X"), only as soft signals.
6. Memory retrieval is **structured** (load all of the candidate's preference rows, which is a few rows) rather than vector search. That is sufficient at this scale and fully deterministic.

## User control
`GET/PUT/DELETE /api/v1/candidates/me/preferences` plus a settings page that lists every
stored preference with its source (`agent`, `settings`, `derived`) and last update time.
