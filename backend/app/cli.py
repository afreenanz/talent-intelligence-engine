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

    p = sub.add_parser("runs", help="list recent ingestion runs")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_runs)

    args = parser.parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
