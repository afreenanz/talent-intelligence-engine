# Evaluation Framework

> Status: **Complete (Milestones 3B–7B, re-measured in 10).** Six evaluations: retrieval, ranking, personalization,
> assistant, résumé extraction and performance. Code: `backend/app/domains/evaluation/`; reports: `eval/reports/`;
> every run is stored in `evaluation_runs` and shown on the in-app Evaluation page (admin).

## Results so far (all produced by committed commands; reports in `eval/reports/`)

| Area | Command | Dataset | Headline (see the report for CIs and caveats) |
|---|---|---|---|
| Retrieval | `eval-retrieval` | retrieval_v1 (synthetic, silver labels, 40 queries) | lexical weakest on both splits; embedding-model choice **not decidable** (flips between splits) |
| Ranking | `eval-ranking` | TalentCLEF 2026 Task A dev (**human labels**, 10 queries) | features + cross-encoder **+0.067 MAP@100** vs hybrid (CI excludes 0) |
| Personalization | `eval-personalization` | simulated personas, synthetic jobs | learned prefs **+0.240** NDCG@10 vs generic (v2, after fixing a feedback loop found in v1) |
| **Agent** | `eval-agent` | agent_v1: 23 scripted conversations, 14 categories | **23/23 passed in two independent runs**; groundedness 1.0; factual consistency 40/40 and 39/39; invalid-arg rate 0; ≈$0.027/run at paid-tier prices |
| **Resume extraction** | `eval-extraction` | extraction_v1: 10 fictional resumes, hand-written expectations | experience in range 10/10; pre-selected skill precision 0.901 → **1.000** after v2 fixes (negation filter, dictionary finds become suggestions) |

| Performance | `bench-performance` | retrieval_v1 queries, real models | HTTP search p50 54 ms (7B) → 63 ms (10, job summaries added); cross-encoder +0.42–0.48 s; HNSW not justified at 1.6k vectors; no cache needed ([performance-benchmarks.md](performance-benchmarks.md)) |

Run any of them from `backend/` with `uv run python -m app.cli <command>` (LLM-backed ones need
`GEMINI_API_KEY`). The empty row in the table above separates quality evaluations from the performance benchmark.

**Scoping:** retrieval and personalization retrieve only from the corpus their labels refer to
(`JobFilters.sources`), so any other listings in the database can't be scored as misses.

**Access:** every run is stored in `evaluation_runs`. The **Evaluation page** in the app (admin) shows the
latest batch of each experiment with its dataset, split, date and commit. `GET /api/v1/evaluations` (admin) lists runs
without per-query payloads; `GET /api/v1/evaluations/{id}` returns everything.
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

## Datasets (`eval/datasets/`, as built)
| Dataset | Files | Content |
|---|---|---|
| `retrieval_v1` | `queries.jsonl`, `qrels.tsv`, `README.md` | 40 queries (`query_id, text, category, split, filters, label_spec`), dev/test split; `qrels.tsv` = `query_id  external_id  grade`, generated from each query's `label_spec` against the synthetic generator's ground truth (**silver** labels; the README explains the rules) |
| TalentCLEF 2026 Task A | downloaded to `data/external/` (git-ignored) by `scripts/fetch_talentclef.py` | 10 job-description queries × 472 synthetic CVs, **human expert binary labels**, CC BY 4.0. The test split's labels are not public (checked Nov 2026) |
| `agent_v1` | `cases.jsonl` | 23 scripted conversations in 14 categories (clear, ambiguous, no match, conflicting preferences, invalid filters, missing profile, injected tool failure, outdated jobs, confirmation and decline, …) with expected/forbidden tools and DB effects |
| `extraction_v1` | `resumes.jsonl`, `README.md` | 10 fictional résumés with hand-written expectations, including a planted prompt injection and negated skills |
| personas | in code (`personalization_eval.py`) | 4 simulated users with fixed liked/disliked role families; relevance from the synthetic generator's ground truth |

## Metrics

| Area | Metrics |
|---|---|
| Structured extraction | JSON validity rate, schema compliance rate, per-field precision/recall (skills as sets), exact match for scalar fields, **hallucinated-field rate** (values not in the source text) |
| Retrieval / ranking | P@K, R@K, MRR, NDCG@K (graded, exponential gain `2^rel − 1`) |
| Agent | tool selection accuracy (expected ⊆ called), invalid-argument rate, tool success rate, task completion, unnecessary calls (called − expected) |
| Response quality | groundedness: share of mentioned jobs that exist in the tool outputs; factual consistency of salary, location and company against DB rows (deterministic string/number checks) |
| Performance | p50/p95 latency per stage, embedding throughput, tokens in/out, estimated cost from a configured price table |

## Reports
Each command writes the `evaluation_runs` row(s) and a Markdown report `eval/reports/<date>-<experiment>.md` with
the configuration, results, confidence intervals and caveats. Reports are committed; the in-app Evaluation page
reads only from `evaluation_runs`. Earlier versions of a report are kept when a fix changed the result
(`…-v1-before-fixes.md`), so the before/after is visible.
