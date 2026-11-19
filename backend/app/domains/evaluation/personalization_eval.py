"""Simulated-persona experiment for personalisation (SYNTHETIC; mechanism check, not user evidence).

Setup
- Every persona has the SAME generic profile (Python, SQL, Git), so generic recommendations are
  identical for all of them. Only personalisation can tailor results.
- Each persona has a hidden taste: liked and disliked role families. Relevance is judged from
  the generator's ground truth (`truth.role_family` in the synthetic file), which is independent
  of the role classifier the system uses.
- Rounds: recommend 20 jobs -> the persona reacts via the REAL service functions (click, save,
  apply, dismiss), which recompute derived preferences -> repeat.
- Evaluation: NDCG@10 over jobs the persona has NOT interacted with ("fresh" jobs), so
  re-showing already-saved jobs can't inflate the score.
- Conditions are paired: same persona and same seed, personalisation off vs on. A third
  condition uses only an explicit stated preference, with no interactions.
Everything runs in one transaction that is rolled back.
"""

import json
import random
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import InteractionType
from app.domains.auth.models import User
from app.domains.candidates.models import CandidateProfile, CandidateSkill
from app.domains.evaluation import metrics as m
from app.domains.evaluation.models import EvaluationRun
from app.domains.evaluation.retrieval_eval import BOOTSTRAP_SAMPLES, git_commit
from app.domains.interactions import service as activity
from app.domains.jobs.models import Job
from app.domains.personalization.adjust import PersonalizationContext
from app.domains.preferences import service as prefs
from app.domains.preferences.schemas import PreferenceKey
from app.domains.ranking.service import rank_jobs
from app.domains.ranking.weighted import WeightedRanker
from app.domains.search.schemas import JobFilters
from app.domains.search.service import retrieve_jobs
from app.domains.skills.repository import resolve_or_create_skills
from app.integrations.embeddings.base import Embedder

ROUNDS = 4
SHOWN = 20
SEEDS = 5
P_CLICK, P_SAVE, P_APPLY, P_DISMISS = 0.9, 0.6, 0.15, 0.6
PERSONAS = {
    "likes backend, dislikes frontend": ({"backend"}, {"frontend"}),
    "likes data, dislikes qa": ({"data"}, {"qa"}),
    "likes ml, dislikes mobile": ({"ml"}, {"mobile"}),
    "likes frontend, dislikes backend": ({"frontend"}, {"backend"}),
}
GENERIC_SKILLS = ["Python", "SQL", "Git"]


@dataclass
class Outcome:
    persona: str
    seed: int
    condition: str
    ndcg10: float
    liked_share: float
    disliked_share: float
    derived: dict[str, Any] = field(default_factory=dict)


def _truth(path: Path) -> dict[str, str]:
    return {
        r["external_id"]: r["truth"]["role_family"]
        for r in map(json.loads, path.open())
        if "truth" in r
    }


def _make_candidate(session: Session, tag: str) -> CandidateProfile:
    # Not a real hash, so a simulated user can never log in. Rolled back anyway.
    user = User(email=f"persona-{tag}@sim.invalid", password_hash="!simulated")  # noqa: S106
    session.add(user)
    session.flush()
    profile = CandidateProfile(
        user_id=user.id, experience_years=Decimal("3"), profile_summary="Software engineer"
    )
    profile.skills = [
        CandidateSkill(skill_id=s.id)
        for s in resolve_or_create_skills(session, GENERIC_SKILLS).values()
    ]
    session.add(profile)
    session.flush()
    return profile


def _recommend(
    session: Session,
    profile: CandidateProfile,
    embedder: Embedder,
    ranker: WeightedRanker,
    personalize: bool,
    k: int,
    source: str,
) -> list[uuid.UUID]:
    ctx = (
        PersonalizationContext.from_preferences(prefs.effective_preferences(session, profile.id))
        if personalize
        else None
    )
    retrieved = retrieve_jobs(
        session,
        query=None,
        candidate_id=profile.id,
        filters=JobFilters(sources=[source]),  # only the labelled synthetic corpus
        top_k=100,
        embedder=embedder,
        extra_lexical_queries=ctx.preference_queries() if ctx else None,
    )
    out = rank_jobs(
        session,
        retrieved,
        ranker=ranker,
        candidate_id=profile.id,
        query=None,
        embedding_model=embedder.spec.name,
        top_k=k,
        personalization=ctx,
        explore_slots=2 if personalize and k == SHOWN else 0,
    )
    return [j.job_id for j in out.jobs]


def _score(
    ranked: list[uuid.UUID],
    family: dict[uuid.UUID, str],
    liked: set[str],
    disliked: set[str],
    exclude: set[uuid.UUID],
) -> tuple[float, float, float]:
    fresh = [j for j in ranked if j not in exclude][:10]
    judgments = {j: 3 for j, f in family.items() if f in liked and j not in exclude}
    ndcg = m.ndcg_at_k(fresh, judgments, 10) if judgments else 0.0
    liked_share = sum(family.get(j) in liked for j in fresh) / max(1, len(fresh))
    disliked_share = sum(family.get(j) in disliked for j in fresh) / max(1, len(fresh))
    return ndcg, liked_share, disliked_share


def run_one(
    session: Session,
    embedder: Embedder,
    ranker: WeightedRanker,
    family: dict[uuid.UUID, str],
    persona: str,
    seed: int,
    condition: str,
    source: str,
) -> Outcome:
    liked, disliked = PERSONAS[persona]
    profile = _make_candidate(session, f"{abs(hash((persona, seed, condition)))}")
    touched: set[uuid.UUID] = set()
    if condition == "explicit preference only":
        prefs.set_explicit(
            session,
            profile.id,
            PreferenceKey.ROLE_CATEGORIES,
            {"prefer": sorted(liked), "avoid": sorted(disliked)},
        )
    else:
        rng = random.Random(seed)  # noqa: S311 (simulation, not security)
        for _ in range(ROUNDS):
            shown = _recommend(
                session,
                profile,
                embedder,
                ranker,
                personalize=condition == "personalized",
                k=SHOWN,
                source=source,
            )
            for pos, jid in enumerate(shown, start=1):
                fam = family.get(jid)
                if jid in touched or fam is None:
                    continue
                if fam in liked and rng.random() < P_CLICK:
                    activity.record_feedback(
                        session, profile.id, jid, InteractionType.CLICK, None, pos
                    )
                    touched.add(jid)
                    if rng.random() < P_SAVE:
                        activity.save_job(session, profile.id, jid)
                    if rng.random() < P_APPLY:
                        activity.apply(session, profile.id, jid, None)
                elif fam in disliked and rng.random() < P_DISMISS:
                    activity.record_feedback(
                        session, profile.id, jid, InteractionType.DISMISS, None, pos
                    )
                    touched.add(jid)
    final = _recommend(
        session,
        profile,
        embedder,
        ranker,
        personalize=condition != "generic",
        k=100,
        source=source,
    )
    ndcg, ls, ds = _score(final, family, liked, disliked, touched)
    derived = {
        r.memory_key: r.memory_value
        for r in prefs.list_preferences(session, profile.id)
        if r.memory_type.value == "derived_preference"
    }
    return Outcome(persona, seed, condition, ndcg, ls, ds, derived)


def run(session: Session, embedder: Embedder, truth_file: Path, source: str) -> list[Outcome]:
    by_ext = _truth(truth_file)
    family = {
        jid: by_ext[ext]
        for jid, ext in session.execute(select(Job.id, Job.external_id).where(Job.source == source))
        if ext in by_ext
    }
    ranker = WeightedRanker.from_file()
    outcomes = []
    for persona in PERSONAS:
        for seed in range(SEEDS):
            for condition in ("generic", "personalized", "explicit preference only"):
                outcomes.append(
                    run_one(session, embedder, ranker, family, persona, seed, condition, source)
                )
    return outcomes


def _paired(outcomes: list[Outcome], a: str, b: str, metric: str) -> tuple[float, float, float]:
    key = {(o.persona, o.seed, o.condition): getattr(o, metric) for o in outcomes}
    pairs = sorted({(o.persona, o.seed) for o in outcomes})
    diffs = [key[(p, s, b)] - key[(p, s, a)] for p, s in pairs]
    rng = random.Random(0)  # noqa: S311
    means = sorted(
        statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(BOOTSTRAP_SAMPLES)
    )
    return (
        statistics.fmean(diffs),
        means[int(0.025 * BOOTSTRAP_SAMPLES)],
        means[int(0.975 * BOOTSTRAP_SAMPLES) - 1],
    )


def persist_and_report(session: Session, outcomes: list[Outcome], report: Path) -> None:
    conditions = ("generic", "personalized", "explicit preference only")
    for c in conditions:
        rows = [o for o in outcomes if o.condition == c]
        session.add(
            EvaluationRun(
                experiment_name="personalization_personas",
                dataset_version="synthetic_jobs_v1",
                split="simulation",
                configuration={
                    "condition": c,
                    "rounds": ROUNDS,
                    "shown": SHOWN,
                    "seeds": SEEDS,
                    "personas": list(PERSONAS),
                },
                metrics={
                    "ndcg@10_fresh": round(statistics.fmean(o.ndcg10 for o in rows), 4),
                    "liked_share@10": round(statistics.fmean(o.liked_share for o in rows), 4),
                    "disliked_share@10": round(statistics.fmean(o.disliked_share for o in rows), 4),
                    "per_run": [o.__dict__ for o in rows],
                },
                git_commit=git_commit(),
            )
        )
    session.commit()

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        "# Personalization: simulated-persona experiment",
        "",
        f"Generated by `python -m app.cli eval-personalization` on {now}, commit `{git_commit()}`.",
        "",
        "> **SIMULATED users on SYNTHETIC jobs.** This checks that the mechanism behaves as",
        "> designed. It is not evidence that real users would benefit.",
        "",
        f"- {len(PERSONAS)} personas x {SEEDS} seeds; identical generic profile "
        f"({', '.join(GENERIC_SKILLS)});",
        f"  {ROUNDS} rounds of {SHOWN} recommendations; behaviour p(click|liked)={P_CLICK},",
        f"  p(save|click)={P_SAVE}, p(apply|click)={P_APPLY}, p(dismiss|disliked)={P_DISMISS}.",
        "- Metric: NDCG@10 over jobs the persona hasn't interacted with; relevance comes from",
        "  generator ground truth.",
        "",
        "## Overall (mean over persona x seed)",
        "",
        "| Condition | NDCG@10 (fresh) | liked share in top 10 | disliked share in top 10 |",
        "|---|---|---|---|",
    ]
    for c in conditions:
        rows = [o for o in outcomes if o.condition == c]
        out.append(
            f"| {c} | {statistics.fmean(o.ndcg10 for o in rows):.3f} | "
            f"{statistics.fmean(o.liked_share for o in rows):.2f} | "
            f"{statistics.fmean(o.disliked_share for o in rows):.2f} |"
        )
    out += [
        "",
        f"## Paired difference vs generic (bootstrap over persona x seed, {BOOTSTRAP_SAMPLES:,} "
        "resamples, 95% CI)",
        "",
        "| Condition | ΔNDCG@10 | Δ liked share |",
        "|---|---|---|",
    ]
    for c in conditions[1:]:
        cells = []
        for metric in ("ndcg10", "liked_share"):
            d, lo, hi = _paired(outcomes, "generic", c, metric)
            cells.append(f"{d:+.3f} [{lo:+.3f}, {hi:+.3f}]" + (" ✱" if lo > 0 or hi < 0 else ""))
        out.append(f"| {c} | " + " | ".join(cells) + " |")
    out += [
        "",
        "## Per persona (NDCG@10, mean over seeds)",
        "",
        "| Persona | generic | personalized | explicit only |",
        "|---|---|---|---|",
    ]
    for p in PERSONAS:
        vals = [
            statistics.fmean(o.ndcg10 for o in outcomes if o.persona == p and o.condition == c)
            for c in conditions
        ]
        out.append(f"| {p} | " + " | ".join(f"{v:.3f}" for v in vals) + " |")
    learned = next(
        (o.derived for o in outcomes if o.condition == "personalized" and o.seed == 0), {}
    )
    out += [
        "",
        "Example of learned preferences (first persona, seed 0):",
        "",
        "```json",
        json.dumps(learned, indent=1),
        "```",
        "",
    ]
    report.write_text("\n".join(out) + "\n")
