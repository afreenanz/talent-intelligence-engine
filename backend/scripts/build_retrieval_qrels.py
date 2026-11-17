"""Build SILVER relevance judgments for eval/datasets/retrieval_v1 from generator ground truth.

Labels come from each query's written `label_spec` and each synthetic job's `truth` field
(role family, seniority, the skills it was generated from) plus its location. Nothing from
any retrieval system is used, so labels are independent of the systems being compared.

Grades:
  3  role family matches and every stated condition (skill, city, seniority, remote) holds
  2  role family matches and at least one, but not all, conditions hold
  1  role family matches only
  0  otherwise (not written; unjudged = non-relevant)

These are "silver" labels: rule-based, not human judgments.
See eval/datasets/retrieval_v1/README.md.

Usage (from backend/):  uv run python -m scripts.build_retrieval_qrels
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.db.enums import LocationType
from app.domains.ingestion.normalize import parse_location

REPO = Path(__file__).resolve().parents[2]
DATASET = REPO / "eval" / "datasets" / "retrieval_v1"
JOBS = REPO / "data" / "synthetic" / "jobs_v1.jsonl"


def grade(spec: dict[str, Any], job: dict[str, Any]) -> int:
    truth = job["truth"]
    if truth["role_family"] not in spec["families"]:
        return 0
    loc = parse_location(job.get("location"))
    skills = set(truth["required"]) | set(truth["preferred"])
    conditions: list[bool] = []
    if spec["skills_any"]:
        conditions.append(bool(skills & set(spec["skills_any"])))
    if spec["city"]:
        conditions.append(loc.city == spec["city"])
    if spec["seniority"]:
        conditions.append(truth["seniority"] == spec["seniority"])
    if spec["remote"]:
        conditions.append(loc.location_type is LocationType.REMOTE)
    if all(conditions):
        return 3
    return 2 if any(conditions) else 1


def main() -> None:
    queries = [json.loads(line) for line in (DATASET / "queries.jsonl").open()]
    jobs = [j for j in map(json.loads, JOBS.open()) if "truth" in j and j.get("external_id")]
    lines, stats = [], {}
    for q in queries:
        grades = Counter()
        for job in jobs:
            g = grade(q["label_spec"], job)
            if g:
                lines.append(f"{q['query_id']}\t{job['external_id']}\t{g}")
                grades[g] += 1
        stats[q["query_id"]] = dict(sorted(grades.items()))
    (DATASET / "qrels.tsv").write_text("query_id\texternal_id\tgrade\n" + "\n".join(lines) + "\n")
    print(f"{len(queries)} queries, {len(jobs)} jobs, {len(lines)} judgments")
    for qid, s in stats.items():
        print(f"  {qid}: {s}")


if __name__ == "__main__":
    main()
