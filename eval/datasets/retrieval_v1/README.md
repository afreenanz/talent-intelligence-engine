# retrieval_v1: silver retrieval benchmark (SYNTHETIC)

| | |
|---|---|
| Corpus | `data/synthetic/jobs_v1.jsonl` (synthetic, seed 42), source `synthetic_v1` |
| Queries | 40 hand-written queries in 7 categories (keyword, natural, abbreviation, skills, location, seniority, filtered), split 21 dev / 19 test, alternating within each category |
| Judgments | `qrels.tsv`, 12,998 graded judgments built by `backend/scripts/build_retrieval_qrels.py` |
| Grades | 3 = role family + all stated conditions (skill/city/seniority/remote); 2 = family + some; 1 = family only; unjudged = 0 |
| Relevant (binary metrics) | grade ≥ 2 |

## How the labels were made, and why they are "silver"
Each query has a written `label_spec` (role families + optional conditions). Grades are computed
from each synthetic job's generator ground truth (`truth` field: role family, seniority, the
exact skills it was generated from) and its location. **No retrieval system output is used**,
so the labels don't favour any system.

## Known weaknesses (read before quoting any number)
1. **Synthetic corpus.** Descriptions come from templates, so wording is far more uniform
   than real postings. Keyword, natural and skill queries are near-saturated (NDCG ≈ 1.0) for every system.
2. **Rule-based relevance.** "Same role family" is a coarse notion of relevance. A human would
   grade many of these differently.
3. **Large relevant sets** (50-300 per query): Recall@10 is necessarily tiny. Use NDCG@10, MRR and Recall@100.
4. **Small samples.** About 20 queries per split; abbreviation (n=4) and location (n=2) queries carry most of
   the signal. Differences under ~0.05 are noise (see the bootstrap intervals).
5. **Author bias.** The queries were written by the same project that built the systems.

Regenerate: `uv run python -m scripts.build_retrieval_qrels` (from `backend/`).
