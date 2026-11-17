"""Generate a SYNTHETIC job dataset for local development and evaluation.

Every record is fictional: companies are invented names, descriptions are assembled from
templates. Nothing here describes a real job or a real employer. Output is deterministic
for a given --seed and --reference-date.

Deliberately injected test cases (ground truth written to the manifest):
- near-duplicates: the same job reposted under a new external_id with light edits
- invalid records: missing or contradictory fields that validation must reject
- already-expired jobs: expires_at before the reference date

Usage (from backend/):
    uv run python scripts/generate_synthetic_jobs.py --n 2000 --seed 42
"""

import argparse
import csv
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

ROLES: dict[str, dict[str, Any]] = {
    "backend": {
        "titles": [
            "Backend Engineer",
            "Software Engineer - Backend",
            "Backend Developer",
            "Python Developer",
            "Java Backend Engineer",
            "Platform Engineer",
        ],
        "core": ["Python", "Java", "Go", "Node.js", "PostgreSQL", "REST APIs", "Microservices"],
        "extra": [
            "FastAPI",
            "Django",
            "Spring Boot",
            "Kafka",
            "Redis",
            "Docker",
            "Kubernetes",
            "AWS",
            "Distributed Systems",
            "gRPC",
            "System Design",
            "MongoDB",
            "GraphQL",
        ],
        "work": [
            "design and build scalable REST and gRPC services",
            "own services end to end, from design review to production on-call",
            "model data and write efficient SQL for high-traffic workloads",
            "improve reliability, latency and observability of core APIs",
            "break a monolith into well-defined services",
            "build event-driven pipelines with message queues",
        ],
        "band": (6, 45),
    },
    "frontend": {
        "titles": [
            "Frontend Engineer",
            "React Developer",
            "UI Engineer",
            "Software Engineer - Frontend",
            "Frontend Developer",
        ],
        "core": ["JavaScript", "TypeScript", "React", "HTML", "CSS"],
        "extra": [
            "Next.js",
            "Redux",
            "Tailwind CSS",
            "Vite",
            "Webpack",
            "Jest",
            "Cypress",
            "Accessibility",
            "Figma",
            "GraphQL",
            "Vue.js",
            "Angular",
        ],
        "work": [
            "build responsive, accessible interfaces used by millions of customers",
            "own the component library and design-system integration",
            "optimise Core Web Vitals and bundle size",
            "collaborate closely with designers on interaction details",
            "write well-tested UI code with strong typing",
        ],
        "band": (5, 40),
    },
    "data": {
        "titles": [
            "Data Engineer",
            "Senior Data Engineer",
            "Analytics Engineer",
            "Big Data Engineer",
        ],
        "core": ["Python", "SQL", "Apache Spark", "Airflow", "ETL"],
        "extra": [
            "dbt",
            "Snowflake",
            "BigQuery",
            "Kafka",
            "AWS",
            "Data Warehousing",
            "Pandas",
            "Hadoop",
            "Docker",
            "Tableau",
        ],
        "work": [
            "build and maintain batch and streaming data pipelines",
            "model the warehouse for analytics and machine learning use cases",
            "own data quality checks and SLAs for critical datasets",
            "partner with analysts and scientists to productionise datasets",
        ],
        "band": (7, 42),
    },
    "ml": {
        "titles": [
            "Machine Learning Engineer",
            "ML Engineer",
            "Applied Scientist",
            "AI Engineer",
            "NLP Engineer",
        ],
        "core": ["Python", "Machine Learning", "PyTorch", "scikit-learn"],
        "extra": [
            "Deep Learning",
            "TensorFlow",
            "Natural Language Processing",
            "Large Language Models",
            "Retrieval-Augmented Generation",
            "MLOps",
            "Hugging Face",
            "Docker",
            "Kubernetes",
            "Recommender Systems",
            "LangChain",
            "Information Retrieval",
            "Vector Databases",
            "Statistics",
        ],
        "work": [
            "train, evaluate and deploy models that power product features",
            "build retrieval and ranking systems over large catalogues",
            "design offline and online evaluation for model quality",
            "ship LLM-based features with guardrails and monitoring",
            "own feature pipelines and model serving infrastructure",
        ],
        "band": (8, 60),
    },
    "devops": {
        "titles": [
            "DevOps Engineer",
            "Site Reliability Engineer",
            "Cloud Engineer",
            "Infrastructure Engineer",
        ],
        "core": ["Linux", "Docker", "Kubernetes", "AWS", "Terraform"],
        "extra": [
            "CI/CD",
            "GitHub Actions",
            "Jenkins",
            "Prometheus",
            "Grafana",
            "Helm",
            "Ansible",
            "Python",
            "Bash",
            "GCP",
            "Azure",
            "Nginx",
            "Observability",
        ],
        "work": [
            "automate infrastructure provisioning with infrastructure as code",
            "run and scale Kubernetes clusters in production",
            "build CI/CD pipelines that ship safely many times a day",
            "own monitoring, alerting and incident response tooling",
        ],
        "band": (6, 45),
    },
    "mobile": {
        "titles": [
            "Android Developer",
            "iOS Developer",
            "Mobile Engineer",
            "Flutter Developer",
            "React Native Developer",
        ],
        "core": ["Kotlin", "Swift", "Android", "iOS"],
        "extra": [
            "Flutter",
            "React Native",
            "Jetpack Compose",
            "SwiftUI",
            "REST APIs",
            "Git",
            "Unit Testing",
            "Dart",
        ],
        "work": [
            "build smooth, offline-friendly mobile experiences",
            "own app performance, crash rates and release quality",
            "work with backend teams on API contracts",
        ],
        "band": (5, 38),
    },
    "qa": {
        "titles": ["QA Engineer", "SDET", "Test Automation Engineer", "Quality Engineer"],
        "core": ["Test Automation", "Selenium", "Python", "Java"],
        "extra": [
            "Playwright",
            "Cypress",
            "Pytest",
            "Performance Testing",
            "CI/CD",
            "REST APIs",
            "Jira",
            "Agile",
        ],
        "work": [
            "design automated test suites for web and API layers",
            "own release quality gates in CI",
            "build performance and load testing harnesses",
        ],
        "band": (4, 28),
    },
}
SENIORITY = [  # (prefix, exp_min, exp_max, band position 0..1, weight)
    ("Junior ", 0, 2, 0.0, 0.18),
    ("", 2, 5, 0.3, 0.42),
    ("Senior ", 5, 9, 0.65, 0.28),
    ("Lead ", 8, 14, 0.9, 0.12),
]
COMPANY_A = [
    "Kestrel",
    "Bluefin",
    "Arcadia",
    "Northwind",
    "Tamarind",
    "Saffron",
    "Lumen",
    "Quillon",
    "Vantara",
    "Orchid",
    "Peregrine",
    "Cobalt",
    "Juniper",
    "Monsoon",
    "Halcyon",
    "Indigo",
    "Zephyr",
    "Coral",
    "Granite",
    "Marigold",
]
COMPANY_B = [
    "Labs",
    "Technologies",
    "Systems",
    "Analytics",
    "Software",
    "Digital",
    "Works",
    "Networks",
    "Pvt Ltd",
    "Technologies Pvt Ltd",
    "Inc",
]
DOMAINS = [
    "fintech",
    "e-commerce",
    "healthtech",
    "edtech",
    "logistics",
    "B2B SaaS",
    "gaming",
    "travel",
    "insurance",
    "media streaming",
]
INDIA_LOCATIONS = [
    "Bangalore, Karnataka, India",
    "Bengaluru",
    "Hyderabad, India",
    "Pune",
    "Mumbai, Maharashtra",
    "Gurgaon",
    "Noida, Uttar Pradesh",
    "Chennai",
    "Kochi, Kerala",
    "Delhi NCR - New Delhi",
    "Remote (India)",
    "Hybrid - Bangalore",
    "Hybrid - Pune",
]
GLOBAL_LOCATIONS = [
    ("Singapore", "SGD", 1),
    ("London, UK", "GBP", 1),
    ("Remote (US)", "USD", 1),
    ("Berlin, Germany", "EUR", 1),
]
GLOBAL_BANDS = {
    "SGD": (60_000, 220_000),
    "GBP": (40_000, 140_000),
    "USD": (90_000, 260_000),
    "EUR": (50_000, 130_000),
}
BENEFITS = [
    "Health insurance for you and your family",
    "Flexible working hours",
    "Annual learning budget",
    "ESOPs",
    "Generous parental leave",
    "Home-office setup allowance",
    "Quarterly team offsites",
]


def _company(rng: random.Random) -> str:
    return f"{rng.choice(COMPANY_A)} {rng.choice(COMPANY_B)}"


def _description(
    rng: random.Random,
    role: dict[str, Any],
    company: str,
    title: str,
    required: list[str],
    preferred: list[str],
    as_html: bool,
) -> str:
    domain = rng.choice(DOMAINS)
    work = rng.sample(role["work"], k=min(len(role["work"]), rng.randint(3, 5)))
    benefits = rng.sample(BENEFITS, k=3)
    intro = (
        f"{company} is a {domain} company building products for customers across India "
        f"and beyond. We are hiring a {title} to join a small, product-focused team."
    )
    req = [f"Strong hands-on experience with {s}" for s in required]
    nice = [f"Exposure to {s}" for s in preferred]
    if as_html:
        li = lambda items: "".join(f"<li>{i}</li>" for i in items)  # noqa: E731
        return (
            f"<p>{intro}</p><h3>What you will do</h3><ul>{li(work)}</ul>"
            f"<h3>What we are looking for</h3><ul>{li(req)}</ul>"
            f"<h3>Nice to have</h3><ul>{li(nice)}</ul>"
            f"<h3>Benefits</h3><ul>{li(benefits)}</ul>"
        )
    bullets = lambda items: "\n".join(f"- {i[0].upper()}{i[1:]}" for i in items)  # noqa: E731
    return (
        f"{intro}\n\nWhat you will do:\n{bullets(work)}\n\nWhat we are looking for:\n"
        f"{bullets(req)}\n\nNice to have:\n{bullets(nice)}\n\nBenefits:\n{bullets(benefits)}"
    )


def _salary_fields(
    rng: random.Random, lpa_lo: float, lpa_hi: float, global_currency: str | None
) -> dict[str, Any]:
    r = rng.random()
    if global_currency:
        lo_band, hi_band = GLOBAL_BANDS[global_currency]
        lo = round(rng.uniform(lo_band, hi_band * 0.7), -3)
        hi = round(lo * rng.uniform(1.15, 1.4), -3)
        return {"salary_min": lo, "salary_max": hi, "salary_currency": global_currency}
    if r < 0.55:
        return {
            "salary_min": int(lpa_lo * 100_000),
            "salary_max": int(lpa_hi * 100_000),
            "salary_currency": "INR",
            "salary_period": "annual",
        }
    if r < 0.75:
        return {"salary_text": f"{lpa_lo:g}-{lpa_hi:g} LPA"}
    if r < 0.88:
        lo, hi = int(lpa_lo * 100_000), int(lpa_hi * 100_000)
        return {"salary_text": f"₹{lo:,} - ₹{hi:,} per annum"}
    return {}  # salary not disclosed


def _experience_fields(rng: random.Random, lo: int, hi: int) -> dict[str, Any]:
    r = rng.random()
    if r < 0.5:
        return {"experience_min": lo, "experience_max": hi}
    if r < 0.9:
        if lo == 0:
            return {"experience_text": rng.choice(["0-2 years", "Fresher / 0-2 yrs"])}
        return {"experience_text": rng.choice([f"{lo}-{hi} years", f"{lo}+ years"])}
    return {}


def generate(n: int, seed: int, reference: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(seed)
    jobs: list[dict[str, Any]] = []
    weights = [s[4] for s in SENIORITY]
    for i in range(n):
        family = rng.choice(list(ROLES))
        role = ROLES[family]
        prefix, exp_lo, exp_hi, pos, _ = rng.choices(SENIORITY, weights=weights)[0]
        base_title = rng.choice(role["titles"])
        title = base_title if base_title.startswith(("Senior", "Lead")) else prefix + base_title
        company = _company(rng)
        is_global = rng.random() < 0.08
        if is_global:
            location, currency, _w = rng.choice(GLOBAL_LOCATIONS)
        else:
            location, currency = rng.choice(INDIA_LOCATIONS), None

        required = rng.sample(role["core"], k=min(len(role["core"]), rng.randint(2, 4)))
        preferred = rng.sample([s for s in role["extra"] if s not in required], k=rng.randint(2, 4))
        band_lo, band_hi = role["band"]
        lpa_lo = round(band_lo + (band_hi - band_lo) * pos * rng.uniform(0.7, 1.0))
        lpa_hi = round(lpa_lo * rng.uniform(1.2, 1.6))

        posted = reference - timedelta(days=rng.randint(0, 60), hours=rng.randint(0, 23))
        record: dict[str, Any] = {
            "external_id": f"syn-{seed}-{i:05d}",
            "title": title,
            "company": company,
            "description": _description(
                rng, role, company, title, required, preferred, as_html=rng.random() < 0.2
            ),
            "location": location,
            "employment_type": rng.choices(
                ["full_time", "contract", "internship"], weights=[0.88, 0.08, 0.04]
            )[0]
            if exp_lo == 0
            else rng.choices(["full_time", "contract"], weights=[0.92, 0.08])[0],
            "posted_at": posted.isoformat(),
            "expires_at": (posted + timedelta(days=rng.randint(30, 90))).isoformat(),
            "synthetic": True,
            "role_family": family,  # ground truth for evaluation; ignored by ingestion
            **_salary_fields(rng, lpa_lo, lpa_hi, currency),
            **_experience_fields(rng, exp_lo, exp_hi),
        }
        if rng.random() < 0.7:  # 30% of postings have no skill list: text extraction must cope
            record["required_skills"] = required
            record["preferred_skills"] = preferred
        jobs.append(record)

    # ---- injected near-duplicates: reposts with a new id and light edits
    duplicates: list[dict[str, str]] = []
    for original in rng.sample(jobs, k=max(1, n // 25)):
        dup = dict(original)
        dup["external_id"] = original["external_id"] + "-repost"
        dup["description"] = original["description"].replace(
            "We are hiring", "We are urgently hiring", 1
        ) + ("\n\nApply today." if "<" not in original["description"] else "<p>Apply today.</p>")
        dup["posted_at"] = (
            datetime.fromisoformat(original["posted_at"]) + timedelta(days=rng.randint(1, 5))
        ).isoformat()
        jobs.append(dup)
        duplicates.append({"duplicate": dup["external_id"], "original": original["external_id"]})

    # ---- injected already-expired jobs
    # Kept disjoint from duplicate originals: dedup only compares against *active* jobs, so an
    # expired original would make its repost a legitimate new job and corrupt the ground truth.
    originals = {d["original"] for d in duplicates}
    expired_ids = []
    pool = [j for j in jobs[:n] if j["external_id"] not in originals]
    for job in rng.sample(pool, k=max(1, n // 20)):
        job["posted_at"] = (reference - timedelta(days=120)).isoformat()
        job["expires_at"] = (reference - timedelta(days=rng.randint(1, 30))).isoformat()
        expired_ids.append(job["external_id"])

    # ---- injected invalid records
    invalid = [
        {
            "external_id": f"syn-{seed}-bad-1",
            "title": "Backend Engineer",
            "company": "Nowhere Labs",
        },
        {
            "external_id": f"syn-{seed}-bad-2",
            "title": "Data Engineer",
            "company": "Nowhere Labs",
            "description": "Short.",
            "location": "Pune",
        },
        {
            "external_id": f"syn-{seed}-bad-3",
            "title": "ML Engineer",
            "company": "Nowhere Labs",
            "description": "A valid-length description for an otherwise broken record.",
            "salary_min": 3_000_000,
            "salary_max": 1_000_000,
            "salary_currency": "INR",
        },
        {
            "external_id": "",
            "title": "QA Engineer",
            "company": "Nowhere Labs",
            "description": "A valid-length description but the external id is missing.",
        },
    ]
    for rec in invalid:
        rec["synthetic"] = True
    jobs.extend(invalid)
    rng.shuffle(jobs)

    manifest = {
        "dataset": "synthetic_jobs_v1",
        "synthetic": True,
        "notice": "All records are fictional and generated from templates.",
        "seed": seed,
        "reference_date": reference.isoformat(),
        "total_records": len(jobs),
        "base_jobs": n,
        "injected": {
            "near_duplicates": duplicates,
            "expired_external_ids": sorted(expired_ids),
            "invalid_external_ids": [r["external_id"] for r in invalid],
        },
    }
    return jobs, manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reference-date", default="2026-11-15")
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "data" / "synthetic"))
    args = parser.parse_args()

    reference = datetime.fromisoformat(args.reference_date).replace(tzinfo=UTC)
    jobs, manifest = generate(args.n, args.seed, reference)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "jobs_v1.jsonl").open("w", encoding="utf-8") as fh:
        for job in jobs:
            fh.write(json.dumps(job, ensure_ascii=False) + "\n")
    (out / "jobs_v1.manifest.json").write_text(json.dumps(manifest, indent=1))

    # Small CSV sample (first 60 valid records) to exercise the CSV path.
    sample = [j for j in jobs if j.get("description", "") and len(j["description"]) > 20][:60]
    fields = [
        "external_id",
        "title",
        "company",
        "description",
        "location",
        "employment_type",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_text",
        "experience_min",
        "experience_max",
        "experience_text",
        "required_skills",
        "preferred_skills",
        "posted_at",
        "expires_at",
    ]
    with (out / "jobs_v1_sample.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for j in sample:
            row = dict(j)
            for key in ("required_skills", "preferred_skills"):
                row[key] = "; ".join(j.get(key, []))
            writer.writerow(row)
    print(
        f"wrote {len(jobs)} records to {out / 'jobs_v1.jsonl'} "
        f"({len(manifest['injected']['near_duplicates'])} near-duplicates, "
        f"{len(manifest['injected']['expired_external_ids'])} expired, "
        f"{len(manifest['injected']['invalid_external_ids'])} invalid)"
    )


if __name__ == "__main__":
    main()
