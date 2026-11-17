"""Operational commands. Run from backend/:  uv run python -m app.cli <command> --help

These are the same service functions the Celery workers will call in Milestone 9.
The CLI is just another thin entry point, like the HTTP routers.
"""

import argparse
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.enums import IngestionMode
from app.db.session import get_sessionmaker
from app.domains.ingestion import service as ingestion
from app.domains.ingestion.models import IngestionRun
from app.domains.ingestion.parsers import read_records
from app.domains.skills.seed import load_taxonomy, seed_skills

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TAXONOMY = REPO_ROOT / "data" / "taxonomy" / "skills_v1.json"
_COUNTS = (
    "received",
    "inserted",
    "updated",
    "unchanged",
    "duplicates",
    "failed",
    "expired",
    "removed",
)


def _print_run(run: IngestionRun) -> None:
    counts = "  ".join(f"{k}={getattr(run, k)}" for k in _COUNTS)
    print(f"run {run.id} [{run.status.value}] source={run.source} mode={run.mode.value}")
    print(f"  {counts}")


def cmd_seed_skills(args: argparse.Namespace) -> int:
    with get_sessionmaker()() as session:
        result = seed_skills(session, load_taxonomy(Path(args.file)))
    print(f"seeded {result.skills} skills and {result.aliases} aliases from {args.file}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 2
    with get_sessionmaker()() as session:
        run = ingestion.ingest(
            session,
            read_records(path),
            source=args.source,
            mode=IngestionMode(args.mode),
            file_name=path.name,
            batch_size=args.batch_size,
        )
        _print_run(run)
    return 0 if run.failed == 0 else 1


def cmd_expire(_: argparse.Namespace) -> int:
    with get_sessionmaker()() as session:
        print(f"expired {ingestion.expire_due_jobs(session)} jobs")
    return 0


def cmd_retry(args: argparse.Namespace) -> int:
    with get_sessionmaker()() as session:
        run = ingestion.retry_failed(
            session, uuid.UUID(args.run_id), include_non_retryable=args.all
        )
        _print_run(run)
    return 0


def cmd_embed_jobs(args: argparse.Namespace) -> int:
    from app.domains.search.indexing import embed_jobs
    from app.integrations.embeddings.sentence_transformer import get_embedder

    embedder = get_embedder()
    with get_sessionmaker()() as session:
        r = embed_jobs(
            session, embedder, batch_size=args.batch_size, include_inactive=args.include_inactive
        )
    print(
        f"model={embedder.spec.name} considered={r.considered} embedded={r.embedded} "
        f"unchanged={r.skipped_unchanged} seconds={r.seconds}"
    )
    return 0


def cmd_eval_retrieval(args: argparse.Namespace) -> int:
    from dataclasses import replace
    from datetime import UTC, datetime

    from app.domains.evaluation import retrieval_eval as ev
    from app.domains.search.indexing import embed_jobs
    from app.integrations.embeddings.base import KNOWN_MODELS
    from app.integrations.embeddings.sentence_transformer import SentenceTransformerEmbedder

    dataset_dir = REPO_ROOT / "eval" / "datasets" / args.dataset
    models = {name: SentenceTransformerEmbedder(KNOWN_MODELS[name]) for name in args.models}
    primary = args.models[0]
    # Ablation: same model and same document vectors, query encoded without the instruction.
    no_prefix = SentenceTransformerEmbedder(replace(KNOWN_MODELS[primary], query_prefix=""))
    with get_sessionmaker()() as session:
        for emb in models.values():  # incremental: only missing/changed vectors are computed
            r = embed_jobs(session, emb)
            print(
                f"embeddings[{emb.spec.name}]: {r.embedded} computed, {r.skipped_unchanged} cached"
            )
        dataset = ev.load_dataset(session, dataset_dir, args.source)
        categories = {q.query_id: q.category for q in dataset.queries}
        best, grid = ev.tune_hybrid(session, dataset, models[primary], primary)
        short = {name: name.split("/")[-1] for name in args.models}
        configs = [ev.Config("lexical (FTS)", "lexical", primary)]
        for name in args.models:
            configs.append(ev.Config(f"dense ({short[name]})", "dense", name))
            configs.append(ev.Config(f"hybrid ({short[name]}, k=60)", "hybrid", name))
        configs.append(
            ev.Config(
                f"hybrid (tuned: {short[primary]}, k={best.rrf_k}, w={best.dense_weight})",
                "hybrid",
                primary,
                best.rrf_k,
                best.dense_weight,
            )
        )
        configs.append(
            ev.Config(
                f"dense ({short[primary]}, NO query prefix)", "dense", primary, query_prefix=False
            )
        )
        results = [
            ev.run_config(
                session, dataset, c, models[c.model] if c.query_prefix else no_prefix, args.split
            )
            for c in configs
        ]
        for res in results:
            ev.persist(
                session,
                "retrieval_comparison",
                dataset,
                args.split,
                res,
                categories,
                {"tuned_on": "dev"},
            )
        stamp = datetime.now(UTC).strftime("%Y-%m-%d")
        report = REPO_ROOT / "eval" / "reports" / f"{stamp}-{args.dataset}-{args.split}.md"
        ev.write_report(report, dataset, args.split, results, results[0], grid, best, categories)
    print(f"report: {report}")
    for res in results:
        print(
            f"  {res.config.name:45} ndcg@10={res.mean('ndcg@10'):.3f} "
            f"mrr@10={res.mean('mrr@10'):.3f} r@100={res.mean('recall@100'):.3f}"
        )
    return 0


def cmd_eval_ranking(args: argparse.Namespace) -> int:
    from datetime import UTC, datetime

    from app.domains.evaluation import ranking_eval as rk
    from app.domains.evaluation.talentclef import load
    from app.domains.ranking.cross_encoder import get_cross_encoder
    from app.domains.ranking.weighted import WeightedRanker
    from app.integrations.embeddings.sentence_transformer import get_embedder

    root = REPO_ROOT / "data" / "external" / "talentclef2026"
    if not (root / "TaskA").exists():
        print("TalentCLEF data not found. Run: uv run python -m scripts.fetch_talentclef")
        return 2
    dataset_name = "talentclef2026_taskA_dev_en"
    ds = load(root, "development", "en")
    with get_sessionmaker()() as session:
        results, info = rk.evaluate(
            session, ds, get_embedder(), get_cross_encoder(), WeightedRanker.from_file()
        )
        rk.persist(session, results, info, dataset_name)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    report = REPO_ROOT / "eval" / "reports" / f"{stamp}-{dataset_name}.md"
    rk.write_report(report, results, info, dataset_name)
    print(f"report: {report}")
    for r in results:
        print(f"  {r.name:50} ndcg@10={r.mean('ndcg@10'):.3f} map@100={r.mean('map@100'):.3f}")
    return 0


def cmd_eval_personalization(_: argparse.Namespace) -> int:
    from datetime import UTC, datetime

    from sqlalchemy.orm import Session

    from app.db.session import get_engine
    from app.domains.evaluation import personalization_eval as pe
    from app.integrations.embeddings.sentence_transformer import get_embedder

    truth = REPO_ROOT / "data" / "synthetic" / "jobs_v1.jsonl"
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    report = REPO_ROOT / "eval" / "reports" / f"{stamp}-personalization-personas.md"
    embedder = get_embedder()
    # Simulated users and their activity live in one transaction that is rolled back.
    connection = get_engine().connect()
    outer = connection.begin()
    try:
        sim = Session(bind=connection, join_transaction_mode="create_savepoint")
        outcomes = pe.run(sim, embedder, truth, "synthetic_v1")
        sim.close()
    finally:
        outer.rollback()
        connection.close()
    with get_sessionmaker()() as session:  # only the evaluation_runs rows are kept
        pe.persist_and_report(session, outcomes, report)
    print(f"report: {report}")
    return 0


def cmd_eval_agent(args: argparse.Namespace) -> int:
    from datetime import UTC, datetime

    from sqlalchemy.orm import Session

    from app.db.session import get_engine
    from app.domains.agent.checkpointer import close_checkpointer
    from app.domains.evaluation import agent_eval as ae
    from app.integrations.embeddings.sentence_transformer import get_embedder
    from app.integrations.llm.factory import get_tool_calling_llm

    llm = get_tool_calling_llm()
    # Pace requests to stay under the free tier's per-minute quota (429s observed at full speed).
    llm.min_interval_seconds = args.min_interval  # type: ignore[attr-defined]
    embedder = get_embedder()
    cases = REPO_ROOT / "eval" / "datasets" / "agent_v1" / "cases.jsonl"
    connection = get_engine().connect()
    outer = connection.begin()  # benchmark users, saves, conversations: all rolled back
    try:
        sim = Session(bind=connection, join_transaction_mode="create_savepoint")
        results = ae.run(sim, cases, llm, embedder)
        summary = ae.summarize(results)
        sim.close()
    finally:
        outer.rollback()
        connection.close()
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    report = REPO_ROOT / "eval" / "reports" / f"{stamp}-agent-benchmark.md"
    with get_sessionmaker()() as session:
        ae.persist_and_report(session, results, summary, llm.model, report)
    close_checkpointer()
    print(f"report: {report}")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


def cmd_eval_extraction(args: argparse.Namespace) -> int:
    from datetime import UTC, datetime

    from app.domains.evaluation import extraction_eval as ee
    from app.integrations.llm.factory import get_llm_provider

    llm = get_llm_provider()
    llm.min_interval_seconds = args.min_interval  # type: ignore[attr-defined]
    dataset = REPO_ROOT / "eval" / "datasets" / "extraction_v1" / "resumes.jsonl"
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    report = REPO_ROOT / "eval" / "reports" / f"{stamp}-resume-extraction.md"
    with get_sessionmaker()() as session:  # read-only use of the skill vocabulary
        results = ee.run(session, dataset, llm)
        summary = ee.summarize(results)
        ee.persist_and_report(session, results, summary, llm.model, report)
    print(f"report: {report}")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


def cmd_bench_performance(_: argparse.Namespace) -> int:
    from datetime import UTC, datetime

    from app.domains.evaluation import performance as perf
    from app.domains.ranking.cross_encoder import get_cross_encoder
    from app.integrations.embeddings.sentence_transformer import get_embedder

    queries = REPO_ROOT / "eval" / "datasets" / "retrieval_v1" / "queries.jsonl"
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    report = REPO_ROOT / "eval" / "reports" / f"{stamp}-performance.md"
    with get_sessionmaker()() as session:
        results = perf.run(session, get_embedder(), get_cross_encoder(), queries)
        session.rollback()
        perf.persist_and_report(session, results, report)
    print(f"report: {report}")
    return 0


def cmd_make_admin(args: argparse.Namespace) -> int:
    from app.domains.auth.models import User

    with get_sessionmaker()() as session:
        user = session.scalar(select(User).where(User.email == args.email.lower()))
        if user is None:
            print(f"no user with email {args.email}", file=sys.stderr)
            return 2
        user.is_admin = True
        session.commit()
    print(f"{args.email} is now an admin")
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    with get_sessionmaker()() as session:
        runs = session.scalars(
            select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(args.limit)
        )
        for run in runs:
            _print_run(run)
    return 0


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("seed-skills", help="load the curated skill taxonomy (idempotent)")
    p.add_argument("--file", default=str(DEFAULT_TAXONOMY))
    p.set_defaults(func=cmd_seed_skills)

    p = sub.add_parser("ingest-jobs", help="import jobs from a .csv / .json / .jsonl file")
    p.add_argument("file")
    p.add_argument("--source", required=True, help="feed name, e.g. synthetic_v1")
    p.add_argument("--mode", choices=[m.value for m in IngestionMode], default="incremental")
    p.add_argument("--batch-size", type=int, default=500)
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("expire-jobs", help="mark jobs past expires_at as expired")
    p.set_defaults(func=cmd_expire)

    p = sub.add_parser("retry-failed", help="re-process failed records of a run")
    p.add_argument("run_id")
    p.add_argument("--all", action="store_true", help="also retry non-retryable failures")
    p.set_defaults(func=cmd_retry)

    p = sub.add_parser("embed-jobs", help="embed jobs whose text changed (incremental)")
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--include-inactive", action="store_true")
    p.set_defaults(func=cmd_embed_jobs)

    p = sub.add_parser("eval-retrieval", help="compare lexical/dense/hybrid on a labelled dataset")
    p.add_argument("--dataset", default="retrieval_v1")
    p.add_argument("--source", default="synthetic_v1", help="job source the judgments refer to")
    p.add_argument("--split", choices=["dev", "test"], default="test")
    p.add_argument(
        "--models",
        nargs="+",
        default=["BAAI/bge-small-en-v1.5", "sentence-transformers/all-MiniLM-L6-v2"],
    )
    p.set_defaults(func=cmd_eval_retrieval)

    p = sub.add_parser("eval-ranking", help="ranking comparison on TalentCLEF 2026 Task A (dev)")
    p.set_defaults(func=cmd_eval_ranking)

    p = sub.add_parser("eval-personalization", help="simulated-persona personalization experiment")
    p.set_defaults(func=cmd_eval_personalization)

    p = sub.add_parser("eval-agent", help="agent benchmark against the live LLM (rolled back)")
    p.add_argument("--min-interval", type=float, default=4.0, help="seconds between LLM calls")
    p.set_defaults(func=cmd_eval_agent)

    p = sub.add_parser("eval-extraction", help="resume extraction benchmark (live LLM)")
    p.add_argument("--min-interval", type=float, default=4.0, help="seconds between LLM calls")
    p.set_defaults(func=cmd_eval_extraction)

    p = sub.add_parser("bench-performance", help="latency, query plans, exact vs HNSW")
    p.set_defaults(func=cmd_bench_performance)

    p = sub.add_parser("make-admin", help="grant admin rights (evaluation dashboard)")
    p.add_argument("email")
    p.set_defaults(func=cmd_make_admin)

    p = sub.add_parser("runs", help="list recent ingestion runs")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_runs)

    args = parser.parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
