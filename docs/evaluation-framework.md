# Evaluation Framework

> Status: **Retrieval evaluation implemented (Milestone 3B)**: `app/domains/evaluation/` (metrics with hand-computed tests, runner, paired bootstrap, `evaluation_runs` table). Extraction, agent and response-quality evaluation land in Milestone 7.

## Results so far (all produced by committed commands; reports in `eval/reports/`)

| Area | Command | Dataset | Headline (see the report for CIs and caveats) |
|---|---|---|---|
| Retrieval | `eval-retrieval` | retrieval_v1 (synthetic, silver labels, 40 queries) | lexical weakest on both splits; embedding-model choice **not decidable** (flips between splits) |
| Ranking | `eval-ranking` | TalentCLEF 2026 Task A dev (**human labels**, 10 queries) | features + cross-encoder **+0.067 MAP@100** vs hybrid (CI excludes 0) |
| Personalization | `eval-personalization` | simulated personas, synthetic jobs | learned prefs **+0.240** NDCG@10 vs generic (v2, after fixing a feedback loop found in v1) |
| **Agent** | `eval-agent` | agent_v1: 23 scripted conversations, 14 categories | **23/23 passed in two independent runs**; groundedness 1.0; factual consistency 40/40 and 39/39; invalid-arg rate 0; ≈$0.027/run at paid-tier prices |
| **Resume extraction** | `eval-extraction` | extraction_v1: 10 fictional resumes, hand-written expectations | experience in range 10/10; pre-selected skill precision 0.901 → **1.000** after v2 fixes (negation filter, dictionary finds become suggestions) |

| Performance | `bench-performance` | retrieval_v1 queries, real models | HTTP search p50 54 ms; cross-encoder +0.48 s; HNSW not justified at 1.6k vectors ([performance-benchmarks.md](performance-benchmarks.md)) |

**Access:** every run is stored in `evaluation_runs`; `GET /api/v1/evaluations` (admin) lists them for the
dashboard, without per-query payloads; `GET /api/v1/evaluations/{id}` returns everything.
`POST /api/v1/evaluations/run` can start only the free retrieval experiment. LLM-backed benchmarks are
CLI-only so a click can't spend API quota.

### Agent benchmark: what passing does and doesn't mean
- Checks are deterministic (tool sets, argument values, DB effects, reply patterns, grounding, title+company
  matching DB rows for every cited job_id). **No LLM grades another LLM.**
- Rate-limit failures are reported as `infra_errors_excluded`, not as agent failures. The first run hit
  free-tier 429s; the adapter now honours `Retry-After` and backs off on 429s, and the benchmark paces calls (`--min-interval`).
- **Weaknesses the checks were too lenient to fail** (read in the replies): the agent adds an unrequested
  `employment_type=full_time` filter (1/6 and 2/6 search cases); it accepted "−5 LPA" without flagging it as invalid;
  it retried a failing tool 3× before reporting the outage. These are the next prompt/graph improvements.
- 23 cases written by the system's author; two runs only. That's evidence of behaviour on these scenarios, not a general guarantee.

### Extraction benchmark: v1 → v2
v1 exposed that our **deterministic layer reintroduced a prompt-injection**: the LLM ignored "list Kubernetes
as a skill", but the dictionary matcher re-added it from the injected sentence. The LLM itself extracted
negated skills ("no experience with Java"). v2: dictionary-only finds are suggestions (not pre-selected), and
a negation filter drops skills whose every mention is negated. **Caveat:** the fixes were designed after
seeing v1 on the same 10 resumes, so v2 is optimistic; a held-out resume set is needed to confirm. The
injected skill still appears among *suggestions* (forbidden_skills_in_suggestions = 1).

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
