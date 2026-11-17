"""Derived (behavioural) preferences, recomputed from the candidate's event log.

Evidence rules (docs/ranking-engine.md, Personalization):
- apply +3, save +2, dismiss -2, unsave -1 (taking back a save is weak negative evidence).
- A click counts (+0.5) only if the same job was later saved or applied to. A bare click is
  curiosity, not preference, and is ignored.
- Impressions without interaction are NOT negative: users skim, and low positions are rarely
  even looked at (position bias).
- Each job contributes once per event type, with exponential time decay (tau = 30 days).
- A category becomes a preference only with support >= MIN_SUPPORT distinct jobs and a
  clearly signed score. Confidence grows with support but stays < 1: derived preferences
  are never as certain as something the candidate told us.
- Explicit preferences are never touched here, and win over derived ones at read time.
"""

import math
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.db.enums import InteractionType, MemorySource, MemoryType
from app.domains.interactions.models import JobInteraction
from app.domains.jobs.models import Job, JobSkill
from app.domains.personalization.categories import job_role_categories
from app.domains.preferences.models import AgentMemory
from app.domains.preferences.schemas import PreferenceKey

EVENT_WEIGHTS = {
    InteractionType.APPLY: 3.0,
    InteractionType.SAVE: 2.0,
    InteractionType.DISMISS: -2.0,
    InteractionType.UNSAVE: -1.0,
}
CONFIRMED_CLICK_WEIGHT = 0.5
DECAY_TAU_DAYS = 30.0
MIN_SUPPORT = 3  # distinct jobs behind a derived category preference
MIN_SCORE = 2.0  # |score| needed to call it a preference
MAX_CONFIDENCE = 0.9
MIN_DISMISSALS_TO_AVOID_COMPANY = 2


def _decay(age_days: float) -> float:
    return math.exp(-max(0.0, age_days) / DECAY_TAU_DAYS)


def compute_category_scores(
    events: list[tuple[uuid.UUID, InteractionType, datetime]],
    categories: dict[uuid.UUID, frozenset[str]],
    now: datetime,
) -> tuple[dict[str, float], dict[str, set[uuid.UUID]]]:
    """Pure function: (job_id, type, time) events -> per-category score and supporting jobs."""
    strong = {
        jid for jid, kind, _ in events if kind in (InteractionType.SAVE, InteractionType.APPLY)
    }
    seen: set[tuple[uuid.UUID, InteractionType]] = set()
    scores: dict[str, float] = defaultdict(float)
    support: dict[str, set[uuid.UUID]] = defaultdict(set)
    for jid, kind, at in sorted(events, key=lambda e: e[2], reverse=True):  # newest first
        if (jid, kind) in seen:
            continue  # one contribution per job per event type
        seen.add((jid, kind))
        if kind is InteractionType.CLICK:
            weight = CONFIRMED_CLICK_WEIGHT if jid in strong else 0.0
        else:
            weight = EVENT_WEIGHTS.get(kind, 0.0)  # impressions -> 0
        if weight == 0.0:
            continue
        w = weight * _decay((now - at).total_seconds() / 86400)
        for cat in categories.get(jid, frozenset()):
            scores[cat] += w
            support[cat].add(jid)
    return dict(scores), dict(support)


def _confidence(support: int) -> float:
    return round(min(MAX_CONFIDENCE, 1 - math.exp(-support / 5)), 3)


def recompute_derived_preferences(
    session: Session, candidate_id: uuid.UUID, now: datetime | None = None
) -> dict[str, dict[str, object]]:
    """Rebuild this candidate's derived rows from scratch (idempotent). Returns what was stored."""
    now = now or datetime.now(UTC)
    events = [
        (r.job_id, r.interaction_type, r.created_at)
        for r in session.execute(
            select(
                JobInteraction.job_id, JobInteraction.interaction_type, JobInteraction.created_at
            ).where(
                JobInteraction.candidate_id == candidate_id,
                JobInteraction.interaction_type != InteractionType.IMPRESSION,
            )
        )
    ]
    job_ids = {jid for jid, _, _ in events}
    jobs = (
        {
            j.id: j
            for j in session.scalars(
                select(Job)
                .where(Job.id.in_(job_ids))
                .options(selectinload(Job.skills).joinedload(JobSkill.skill))
            )
        }
        if job_ids
        else {}
    )
    categories = {
        jid: frozenset(
            c.value for c in job_role_categories(j.title, (s.skill.category for s in j.skills))
        )
        for jid, j in jobs.items()
    }
    scores, support = compute_category_scores(events, categories, now)

    prefer = sorted(
        c for c, s in scores.items() if s >= MIN_SCORE and len(support[c]) >= MIN_SUPPORT
    )
    avoid = sorted(
        c for c, s in scores.items() if s <= -MIN_SCORE and len(support[c]) >= MIN_SUPPORT
    )
    stored: dict[str, dict[str, object]] = {}
    rows = []
    if prefer or avoid:
        n = max(len(support[c]) for c in (*prefer, *avoid))
        value: dict[str, object] = {
            "prefer": prefer,
            "avoid": avoid,
            "evidence": {
                c: {"score": round(scores[c], 2), "jobs": len(support[c])}
                for c in (*prefer, *avoid)
            },
        }
        rows.append((PreferenceKey.ROLE_CATEGORIES, value, _confidence(n)))

    dismissed_by_company: dict[str, set[uuid.UUID]] = defaultdict(set)
    positive_companies = {
        jobs[j].company
        for j, k, _ in events
        if j in jobs and k in (InteractionType.SAVE, InteractionType.APPLY)
    }
    for jid, kind, _ in events:
        if kind is InteractionType.DISMISS and jid in jobs:
            dismissed_by_company[jobs[jid].company].add(jid)
    avoid_companies = sorted(
        c
        for c, js in dismissed_by_company.items()
        if len(js) >= MIN_DISMISSALS_TO_AVOID_COMPANY and c not in positive_companies
    )
    if avoid_companies:
        rows.append(
            (
                PreferenceKey.COMPANY_AVOID,
                {"companies": avoid_companies},
                _confidence(min(len(dismissed_by_company[c]) for c in avoid_companies)),
            )
        )

    session.execute(
        delete(AgentMemory).where(
            AgentMemory.candidate_id == candidate_id,
            AgentMemory.memory_type == MemoryType.DERIVED_PREFERENCE,
        )
    )
    for key, value, confidence in rows:
        session.execute(
            insert(AgentMemory).values(
                candidate_id=candidate_id,
                memory_type=MemoryType.DERIVED_PREFERENCE,
                memory_key=key.value,
                memory_value=value,
                confidence=confidence,
                source=MemorySource.DERIVED,
            )
        )
        stored[key.value] = {"value": value, "confidence": confidence}
    session.commit()
    return stored
