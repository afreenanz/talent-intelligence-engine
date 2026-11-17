"""Turn features into plain-language reasons. Every sentence is derived from a computed feature,
never generated, so explanations can't claim something the ranker didn't use."""

from app.domains.ranking.features import FeatureVector, JobFacts


def explain(
    fv: FeatureVector,
    contributions: dict[str, float],
    job: JobFacts,
    skill_names: dict[int, str],
    has_candidate: bool,
) -> list[str]:
    reasons: list[str] = []
    v = fv.values
    if has_candidate and job.core_skill_ids and "required_skill_coverage" not in fv.missing:
        matched = sorted(skill_names.get(s, str(s)) for s in fv.matched_core)
        lacking = sorted(skill_names.get(s, str(s)) for s in fv.missing_core)
        label = "required" if job.required_skill_ids else "key"
        line = f"Matches {len(matched)} of {len(job.core_skill_ids)} {label} skills"
        if matched:
            line += f" ({', '.join(matched[:5])})"
        reasons.append(line)
        if lacking:
            reasons.append(f"Missing: {', '.join(lacking[:5])}")
    if "experience_fit" not in fv.missing:
        if v["experience_fit"] == 1.0:
            reasons.append("Your experience is within the required range")
        elif v["experience_fit"] < 0.5:
            reasons.append("Your experience is outside the required range")
    if "salary_fit" not in fv.missing:
        reasons.append(
            "Salary meets your minimum"
            if v["salary_fit"] >= 1.0
            else "Salary may be below your minimum"
        )
    if "location_fit" not in fv.missing:
        if v["location_fit"] >= 0.8:
            reasons.append("Location fits your preference")
        elif v["location_fit"] <= 0.2:
            reasons.append("Location doesn't match your preference")
    if "semantic_similarity" not in fv.missing and v["semantic_similarity"] >= 0.75:
        reasons.append("Strong overall match with your profile or query")
    if "recency" not in fv.missing and v["recency"] >= 0.8:
        reasons.append("Posted recently")
    unknown = sorted(fv.missing - {"retrieval_score", "preferred_skill_coverage", "skill_jaccard"})
    if unknown:
        reasons.append(
            "Not enough information to judge: " + ", ".join(u.replace("_", " ") for u in unknown)
        )
    top = max(contributions, key=lambda k: contributions[k])
    reasons.append(f"Biggest factor: {top.replace('_', ' ')}")
    return reasons
