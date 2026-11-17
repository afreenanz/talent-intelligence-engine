# Data provenance

Every dataset in this folder, where it came from, and whether it may be used.

| Path | Origin | Real or synthetic | Licence / use |
|---|---|---|---|
| `taxonomy/skills_v1.json` | Hand-written for this project | n/a (vocabulary) | Project-owned |
| `synthetic/jobs_v1.jsonl` | `backend/scripts/generate_synthetic_jobs.py --n 2000 --seed 42 --reference-date 2026-11-15` | **SYNTHETIC**. All companies and postings are fictional | Project-owned |
| `synthetic/jobs_v1.manifest.json` | Same script | Ground truth for injected duplicates, expired and invalid records | Project-owned |
| `synthetic/jobs_v1_sample.csv` | Same script (first 60 valid records) | **SYNTHETIC** | Project-owned |

Rules:
- Synthetic records carry `"synthetic": true`. The fictional company names are invented and any
  resemblance to a real organisation is coincidental.
- No real resumes or personal data are committed. `data/private/` is git-ignored for local use.
- A public dataset may be added only after its licence is checked and recorded in this table.
- Regenerating with the same arguments produces a byte-identical file (verified with md5).
