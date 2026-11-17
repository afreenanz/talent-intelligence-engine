# Data provenance

Every dataset in this folder, where it came from, and whether it may be used.

| Path | Origin | Real or synthetic | Licence / use |
|---|---|---|---|
| `taxonomy/skills_v1.json` | Hand-written for this project | n/a (vocabulary) | Project-owned |
| `synthetic/jobs_v1.jsonl` | `backend/scripts/generate_synthetic_jobs.py --n 2000 --seed 42 --reference-date 2026-11-15` | **SYNTHETIC**. All companies and postings are fictional | Project-owned |
| `synthetic/jobs_v1.manifest.json` | Same script | Ground truth for injected duplicates, expired and invalid records | Project-owned |
| `external/talentclef2026/` (**not committed**; `uv run python -m scripts.fetch_talentclef`) | TalentCLEF 2026 Task A, Zenodo record 19652670 v0.3.0, checksum-pinned | CVs are **synthetic** (per the organisers); job descriptions derived from real postings; relevance labels by human experts | **CC BY 4.0**. Attribution: *TalentCLEF 2026 organisers, "TalentCLEF 2026 corpus: Skill and Job Title Intelligence for Human Capital Management", Zenodo, 2026.* |
| `synthetic/jobs_v1_sample.csv` | Same script (first 60 valid records) | **SYNTHETIC** | Project-owned |

Rules:
- Synthetic records carry `"synthetic": true` and a `truth` object (role family, seniority, generating skills) used only to build evaluation labels; ingestion ignores it. The fictional company names are invented and any
  resemblance to a real organisation is coincidental.
- No real resumes or personal data are committed. `data/private/` is git-ignored for local use.
- A public dataset may be added only after its licence is checked and recorded in this table.
- Regenerating with the same arguments produces a byte-identical file (verified with md5).
