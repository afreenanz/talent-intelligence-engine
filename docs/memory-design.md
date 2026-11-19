# Memory Design

> Status: **As built (Milestones 5A, 5B, 6A; documentation pass after 10).** Code:
> `app/domains/preferences/` (vocabulary, service, API), `app/domains/personalization/derived.py`
> (learned preferences), `app/domains/agent/` (conversations and the `update_candidate_preferences` tool).
> Decision record: ADR-009.

## What the system remembers, and where

| Kind | Store | Lifetime | Written by | User control |
|---|---|---|---|---|
| Conversation history | `conversations`, `messages` (ordered by `seq`) | until the conversation is deleted | the agent service, after each turn | list, open, delete (Assistant page) |
| Agent execution state | LangGraph `PostgresSaver` tables, `langgraph` schema | per conversation thread | LangGraph | none needed (internal); removed with the conversation's data |
| Stated preferences | `agent_memory`, `memory_type = explicit_preference` | until changed or removed | the Preferences page (`source = settings`) or the assistant after the user confirms (`source = agent`) | change or remove any of them |
| Learned preferences | `agent_memory`, `memory_type = derived_preference` | rebuilt after every click, save, unsave, application or "not interested" | `recompute_derived_preferences` (same request, same transaction) | override with a stated preference; shown with confidence on the Preferences page |
| Profile facts | `candidate_profiles`, `candidate_skills` | until changed | résumé review, profile edits | yes |

## The preference vocabulary (fixed, validated)
Only these keys can be stored, each with its own Pydantic model (`app/domains/preferences/schemas.py`).
An invalid value is rejected with a 422 and field details.

| Key | Value |
|---|---|
| `role_categories` | `{prefer: [...], avoid: [...]}` from backend, frontend, fullstack, data, ml, devops, mobile, qa, security, design, product; a category can't be in both lists |
| `locations` | `{cities: [...]}` (1–10) |
| `location_type` | `{value: onsite | remote | hybrid}` |
| `min_salary` | `{amount, currency}` (annual, whole units; INR by default) |
| `employment_type` | `{value: full_time | part_time | contract | internship | temporary}` |
| `company_avoid` | `{companies: [...]}` |
| `skills_to_use` | `{skills: [...]}` |

Free-text "facts" ("I like small teams") are deliberately **not** stored: they can't be validated, and
the ranker couldn't use them.

## Rules
1. **Nothing becomes memory just because it was said.** The assistant can only write a preference through
   the `update_candidate_preferences` tool, which pauses on a LangGraph `interrupt()` until the user approves
   it on a confirmation card that describes the change in plain words.
2. **Upsert, never duplicate:** unique on `(candidate_id, memory_type, memory_key)`. Every write returns the
   previous value, so the assistant can say "changed from X to Y".
3. **Stated beats learned.** For the same key, an explicit preference always wins at read time
   (`effective_preferences`). Learned preferences never overwrite stated ones.
4. **Learned preferences need evidence.** A role category is learned only from at least 3 distinct jobs
   (`MIN_SUPPORT`) with a clearly signed score; confidence grows with support but stays below 1. Only
   explicit actions count as evidence (clicks, saves, applications, "not interested"); merely being shown
   a job is never treated as a dislike.
5. **Bounded influence.** Preferences adjust a job's score by at most ±0.1 in ranking, and add a preference
   retrieval channel plus two exploration slots, so the list can't collapse onto one category
   (ranking-engine.md, Personalization).
6. **Structured recall.** Memory is loaded as the candidate's few preference rows, not by vector search:
   deterministic and enough at this scale.

**Not built (changed from design):** the design said a request contradicting a stated preference would
trigger a confirmation that names the conflict. Every preference change is confirmed, but the card shows
the new value, not the old one; the previous value appears in the assistant's reply after the change.

## User control
- `GET /api/v1/candidates/me/preferences` returns everything stored, stated and learned, with source,
  confidence and update time.
- `PUT` / `DELETE /api/v1/candidates/me/preferences/{key}` set or remove a stated preference (learned ones
  can't be deleted directly; a stated preference overrides them).
- The **Preferences page** lists all seven keys; learned values are shown with their confidence, and struck
  through when a stated preference overrides them.
- Deleting the account (a database cascade; there's no endpoint yet, see security.md) removes all of it.
