"""Resume extraction benchmark: raw LLM output vs the post-processed (grounded) result.

Scored deterministically against hand-written expectations (eval/datasets/extraction_v1).
Reporting both stages shows exactly what the deterministic checks add on top of the LLM.
"""

import json
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.evaluation.models import EvaluationRun
from app.domains.evaluation.retrieval_eval import git_commit
from app.domains.resumes.postprocess import _fold, appears_in, postprocess
from app.domains.resumes.prompts import RESUME_EXTRACTION_VERSION, build_resume_prompt
from app.domains.resumes.schemas import ResumeExtraction
from app.domains.skills.extraction import build_matcher
from app.domains.skills.models import Skill
from app.domains.skills.normalization import normalize_skill_name
from app.domains.skills.repository import lookup_skills
from app.integrations.llm.base import LLMError, LLMProvider

REFERENCE_DATE = date(2026, 11, 18)  # the date the expectations were computed for


@dataclass
class ExtractionResult:
    resume_id: str
    note: str
    schema_valid: bool
    error: str | None
    scores: dict[str, Any]
    latency_ms: int
    input_tokens: int
    output_tokens: int


def _norm_set(values: list[str]) -> set[str]:
    return {normalize_skill_name(v) for v in values if v}


def _canon(session: Session, names: set[str]) -> set[str]:
    """Map names through the alias table (so "postgres" and "PostgreSQL" compare equal)."""
    resolved = lookup_skills(session, list(names))
    return {resolved[n][1].lower() if n in resolved else n for n in names}


def _pr(pred: set[str], gold: set[str]) -> tuple[float, float]:
    if not pred:
        return (1.0 if not gold else 0.0), (1.0 if not gold else 0.0)
    tp = len(pred & gold)
    return tp / len(pred), (tp / len(gold) if gold else 1.0)


def score(
    session: Session, text: str, gold: dict[str, Any], raw: ResumeExtraction
) -> dict[str, Any]:
    matcher = build_matcher(session)
    found = matcher.find(text)
    dictionary = dict(
        session.execute(select(Skill.id, Skill.name).where(Skill.id.in_(found))).all()
    )
    parsed = postprocess(
        raw,
        text,
        resolve_skills=lambda n: lookup_skills(session, n),
        dictionary_skills=dictionary,
        today=REFERENCE_DATE,
        prompt_version=RESUME_EXTRACTION_VERSION,
    )
    folded = _fold(text)
    gold_skills = _canon(session, _norm_set(gold["skills"]))
    raw_skills = _canon(session, _norm_set(raw.skills))
    # "final" = what is pre-selected for the profile; dictionary suggestions are reported apart.
    final_skills = _canon(session, _norm_set([s.name for s in parsed.skills if not s.suggested]))
    suggested = _canon(session, _norm_set([s.name for s in parsed.skills if s.suggested]))
    must_not = _canon(session, _norm_set(gold.get("must_not_have", [])))
    raw_p, raw_r = _pr(raw_skills, gold_skills)
    fin_p, fin_r = _pr(final_skills, gold_skills)

    companies = [(w.company or "").lower() for w in parsed.work_experience]
    gold_companies = [c.lower() for c in gold["companies"]]
    company_recall = (
        (
            sum(any(g in c or c in g for c in companies if c) for g in gold_companies)
            / len(gold_companies)
        )
        if gold_companies
        else (1.0 if not companies else 0.0)
    )
    current = [(w.company or "").lower() for w in parsed.work_experience if w.is_current]
    gc = (gold.get("current_company") or "").lower()
    current_ok = (
        (any(gc in c or c in gc for c in current) and len(current) == 1) if gc else not current
    )
    starts = [w.start_date or "" for w in parsed.work_experience]
    start_hits = sum(any(s == g or s.startswith(g) for s in starts) for g in gold["work_starts"])
    lo, hi = gold["experience_years_min"], gold["experience_years_max"]
    exp = parsed.experience_years
    exp_ok = (exp is None) if lo is None else (exp is not None and lo <= exp <= hi)
    inst = [e.institution.lower() for e in parsed.education]
    inst_recall = (
        (
            sum(any(g.lower() in i for i in inst) for g in gold["institutions"])
            / len(gold["institutions"])
        )
        if gold["institutions"]
        else 1.0
    )
    gname = gold["full_name"]
    name_ok = (
        (parsed.full_name is None)
        if gname is None
        else (
            parsed.full_name is not None
            and " ".join(parsed.full_name.split()).lower() == gname.lower()
        )
    )
    return {
        "name_correct": name_ok,
        "skills_raw_precision": round(raw_p, 3),
        "skills_raw_recall": round(raw_r, 3),
        "skills_final_precision": round(fin_p, 3),
        "skills_final_recall": round(fin_r, 3),
        "raw_skills_not_in_text": sorted(
            s for s in _norm_set(raw.skills) if not appears_in(s, folded)
        ),
        "forbidden_in_raw": sorted(must_not & raw_skills),
        "forbidden_in_final": sorted(must_not & final_skills),
        "forbidden_in_suggestions": sorted(must_not & suggested),
        "suggested": sorted(suggested),
        "company_recall": round(company_recall, 3),
        "current_job_correct": current_ok,
        "start_dates_correct": f"{start_hits}/{len(gold['work_starts'])}",
        "experience_years": exp,
        "experience_in_expected_range": exp_ok,
        "institution_recall": round(inst_recall, 3),
        "warnings": parsed.warnings,
    }


def run(session: Session, dataset: Path, llm: LLMProvider) -> list[ExtractionResult]:
    out = []
    for row in map(json.loads, dataset.open()):
        t = time.perf_counter()
        try:
            res = llm.generate_structured(build_resume_prompt(row["text"]), ResumeExtraction)
        except LLMError as exc:
            out.append(
                ExtractionResult(
                    row["resume_id"],
                    row["note"],
                    False,
                    str(exc),
                    {},
                    int((time.perf_counter() - t) * 1000),
                    0,
                    0,
                )
            )
            continue
        out.append(
            ExtractionResult(
                row["resume_id"],
                row["note"],
                True,
                None,
                score(session, row["text"], row["gold"], res.value),
                res.usage.latency_ms,
                res.usage.input_tokens or 0,
                res.usage.output_tokens or 0,
            )
        )
    return out


def summarize(results: list[ExtractionResult]) -> dict[str, Any]:
    ok = [r for r in results if r.schema_valid]
    if not ok:
        return {"resumes": len(results), "schema_valid_rate": 0.0}

    def mean(k: str) -> float:
        return round(statistics.fmean(float(r.scores[k]) for r in ok), 3)

    return {
        "resumes": len(results),
        "schema_valid_rate": round(len(ok) / len(results), 3),
        "name_accuracy": mean("name_correct"),
        "skills_precision_raw_llm": mean("skills_raw_precision"),
        "skills_precision_after_checks": mean("skills_final_precision"),
        "skills_recall_raw_llm": mean("skills_raw_recall"),
        "skills_recall_after_checks": mean("skills_final_recall"),
        "raw_llm_skills_not_in_text": sum(len(r.scores["raw_skills_not_in_text"]) for r in ok),
        "forbidden_skills_raw": sum(len(r.scores["forbidden_in_raw"]) for r in ok),
        "forbidden_skills_final": sum(len(r.scores["forbidden_in_final"]) for r in ok),
        "forbidden_skills_in_suggestions": sum(
            len(r.scores["forbidden_in_suggestions"]) for r in ok
        ),
        "company_recall": mean("company_recall"),
        "current_job_accuracy": mean("current_job_correct"),
        "experience_in_range": mean("experience_in_expected_range"),
        "institution_recall": mean("institution_recall"),
        "latency_ms_median": int(statistics.median(r.latency_ms for r in ok)),
        "tokens_in": sum(r.input_tokens for r in ok),
        "tokens_out_incl_thinking": sum(r.output_tokens for r in ok),
    }


def persist_and_report(
    session: Session,
    results: list[ExtractionResult],
    summary: dict[str, Any],
    model: str,
    report: Path,
) -> None:
    session.add(
        EvaluationRun(
            experiment_name="resume_extraction",
            dataset_version="extraction_v1",
            split="all",
            configuration={
                "model": model,
                "prompt_version": RESUME_EXTRACTION_VERSION,
                "reference_date": REFERENCE_DATE.isoformat(),
            },
            metrics={"summary": summary, "per_resume": [r.__dict__ for r in results]},
            git_commit=git_commit(),
        )
    )
    session.commit()
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        "# Resume extraction benchmark: extraction_v1",
        "",
        f"Generated by `python -m app.cli eval-extraction` on {now}, commit `{git_commit()}`, "
        f"model `{model}`, prompt `{RESUME_EXTRACTION_VERSION}`.",
        "Fictional resumes, hand-written expectations. *Raw* = the LLM's output;",
        "*after checks* = after deterministic grounding and computed experience",
        "(what the product actually stores).",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        *[f"| {k.replace('_', ' ')} | {v} |" for k, v in summary.items()],
        "",
        "## Per resume",
        "",
        "| Resume | What it tests | Name | Skills P/R (raw → final) | Not in text (raw) "
        "| Forbidden raw → final | Experience | In range |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if not r.schema_valid:
            out.append(f"| {r.resume_id} | {r.note} | schema invalid: {r.error} | | | | | |")
            continue
        s = r.scores
        out.append(
            f"| {r.resume_id} | {r.note} | {'✅' if s['name_correct'] else '❌'} | "
            f"{s['skills_raw_precision']:.2f}/{s['skills_raw_recall']:.2f} → "
            f"{s['skills_final_precision']:.2f}/{s['skills_final_recall']:.2f} | "
            f"{', '.join(s['raw_skills_not_in_text']) or '-'} | "
            f"{', '.join(s['forbidden_in_raw']) or '-'} → "
            f"{', '.join(s['forbidden_in_final']) or '-'} | "
            f"{s['experience_years']} | {'✅' if s['experience_in_expected_range'] else '❌'} |"
        )
    report.write_text("\n".join(out) + "\n")
