# Evaluation Framework

> Status: **Design (Milestone 0)**. Metric functions are built and unit-tested from Milestone 3; the full framework lands in Milestone 7.

## Principles
- Metrics are pure functions with unit tests against hand-computed examples.
- Every run records `experiment_name, dataset_version, configuration, metrics, git_commit` in `evaluation_runs`.
- Dev/test split of queries. Tuning on dev, reporting on test.
- Differences between pipelines are reported with a **paired bootstrap confidence interval over queries**, not as bare point estimates.
- LLM-as-judge is never the only signal. Where it is used, its agreement with human labels is reported.

## Datasets (`eval/datasets/<version>/`)
| File | Content |
|---|---|
| `jobs.jsonl` | Frozen job corpus snapshot (synthetic, labelled as such) |
| `queries.jsonl` | `{query_id, text, filters, candidate_ref?, split}` |
| `qrels.tsv` | `query_id  job_id  grade(0–3)`, labelled by pooling |
| `extraction_gold/` | Resume texts + hand-written expected JSON |
| `agent_cases.jsonl` | `{case_id, user_turns, expected_tools, forbidden_tools, expected_outcome, category}` |

The categories in `agent_cases` follow the brief: clear, ambiguous, no-match, conflicting preferences, invalid filters, missing profile, tool failure (injected), outdated jobs.

## Metrics

| Area | Metrics |
|---|---|
| Structured extraction | JSON validity rate, schema compliance rate, per-field precision/recall (skills as sets), exact match for scalar fields, **hallucinated-field rate** (values not in the source text) |
| Retrieval / ranking | P@K, R@K, MRR, NDCG@K (graded, exponential gain `2^rel − 1`) |
| Agent | tool selection accuracy (expected ⊆ called), invalid-argument rate, tool success rate, task completion, unnecessary calls (called − expected) |
| Response quality | groundedness: share of mentioned jobs that exist in the tool outputs; factual consistency of salary, location and company against DB rows (deterministic string/number checks) |
| Performance | p50/p95 latency per stage, embedding throughput, tokens in/out, estimated cost from a configured price table |

## Reports
`python -m app.domains.evaluation.run --experiment retrieval_v1` writes the DB row plus
`eval/reports/<date>-<experiment>.md`. The evaluation dashboard reads only from `evaluation_runs`.
