# extraction_v1: resume extraction benchmark (FICTIONAL)

10 hand-written fictional resumes with hand-written expected values (`resumes.jsonl`). All names,
companies and contact details are invented. Experience ranges are computed by hand from the dated work
history, with the reference date 2026-11-18 (the date the benchmark was written). They are ranges because
"Present" moves.

Each resume targets one behaviour (see `note`): baseline, no work history, overlapping jobs, year-only
dates, prompt injection, negated skills, missing name, messy formatting, a career gap, and a summary that
over-claims experience.

Limitations: small (n=10), written by the system's author, English only, plain-text resumes (no PDF layout).
