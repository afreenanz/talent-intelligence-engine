from decimal import Decimal

import pytest

from app.db.enums import LocationType
from app.domains.ingestion import normalize as n

# ---------------------------------------------------------------- salary


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15-25 LPA", (1_500_000, 2_500_000, "INR")),
        ("12 LPA", (1_200_000, 1_200_000, "INR")),
        ("₹8,00,000 - ₹12,00,000 per annum", (800_000, 1_200_000, "INR")),
        ("INR 6 lakhs - 9 lakhs", (600_000, 900_000, "INR")),
        ("1.2 - 1.8 Cr", (12_000_000, 18_000_000, "INR")),
        ("$120k - $150k", (120_000, 150_000, "USD")),
        ("50,000/month INR", (600_000, 600_000, "INR")),
        ("$40 per hour", (83_200, 83_200, "USD")),
        ("£55k", (55_000, 55_000, "GBP")),
    ],
)
def test_parse_salary_text(text: str, expected: tuple[int, int, str]) -> None:
    parsed = n.parse_salary_text(text)
    assert (parsed.minimum, parsed.maximum, parsed.currency) == expected


@pytest.mark.parametrize("text", ["Competitive", "", None, "25-15 LPA", "DOE"])
def test_unparseable_or_inverted_salary_is_none_not_a_guess(text: str | None) -> None:
    parsed = n.parse_salary_text(text)
    assert parsed.minimum is None and parsed.maximum is None


def test_salary_without_currency_marker_uses_default_only_if_given() -> None:
    assert n.parse_salary_text("100000 - 150000").minimum is None
    assert n.parse_salary_text("100000 - 150000", default_currency="INR").currency == "INR"


def test_annualize() -> None:
    assert n.annualize(100_000, "monthly") == 1_200_000
    assert n.annualize(50, "hourly") == 104_000
    assert n.annualize(None, "annual") is None


# ---------------------------------------------------------------- experience


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2-5 years", (Decimal(2), Decimal(5))),
        ("3+ yrs", (Decimal(3), None)),
        ("Minimum 4 years", (Decimal(4), None)),
        ("Fresher", (Decimal(0), Decimal(1))),
        ("1.5 years", (Decimal("1.5"), Decimal("1.5"))),
        ("8 - 3 years", (None, None)),  # inverted -> unknown, not swapped
        ("lots of experience", (None, None)),
        ("100 years", (None, None)),
    ],
)
def test_parse_experience_text(text: str, expected: tuple[Decimal | None, Decimal | None]) -> None:
    assert n.parse_experience_text(text) == expected


# ---------------------------------------------------------------- location


@pytest.mark.parametrize(
    ("raw", "city", "country", "loc_type"),
    [
        ("Bangalore, Karnataka, India", "Bengaluru", "India", None),
        ("Bengaluru", "Bengaluru", "India", None),
        ("Gurgaon", "Gurugram", "India", None),
        ("Remote (India)", None, "India", LocationType.REMOTE),
        ("Hybrid - Pune", "Pune", "India", LocationType.HYBRID),
        ("Delhi NCR - New Delhi", "Delhi", "India", None),
        ("London, UK", "London", "United Kingdom", None),
        ("Atlantis", None, None, None),
        (None, None, None, None),
    ],
)
def test_parse_location(
    raw: str | None, city: str | None, country: str | None, loc_type: LocationType | None
) -> None:
    assert n.parse_location(raw) == n.ParsedLocation(city, country, loc_type)


# ---------------------------------------------------------------- titles / companies


def test_normalize_title_expands_abbreviations_but_keeps_seniority() -> None:
    assert n.normalize_title("Sr. Backend Engg (Python)") == "senior backend engineer python"
    assert n.normalize_title("SWE II") == "software engineer ii"
    assert n.normalize_title("Senior Data Engineer") != n.normalize_title("Junior Data Engineer")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Kestrel Technologies Pvt Ltd", "kestrel technologies"),
        ("Kestrel Technologies Private Limited", "kestrel technologies"),
        ("Bluefin Inc.", "bluefin"),
        ("Acme, LLC", "acme"),
        ("Coral", "coral"),
    ],
)
def test_normalize_company(raw: str, expected: str) -> None:
    assert n.normalize_company(raw) == expected


# ---------------------------------------------------------------- description


def test_clean_description_strips_html_and_keeps_structure() -> None:
    raw = "<p>Hello&nbsp;<b>world</b> &amp; friends</p><ul><li>One</li><li>Two</li></ul>"
    assert n.clean_description(raw) == "Hello world & friends\n\n- One\n\n- Two"


def test_clean_description_plain_text_whitespace() -> None:
    assert n.clean_description("  a   b \r\n\r\n\r\n c  ") == "a b\n\nc"


def test_clean_description_does_not_treat_comparisons_as_html() -> None:
    assert n.clean_description("latency < 50ms and throughput > 1k rps") == (
        "latency < 50ms and throughput > 1k rps"
    )


# ---------------------------------------------------------------- similarity / hashing


def test_jaccard_on_shingles() -> None:
    a = n.shingles("we are hiring a backend engineer to build scalable services")
    b = n.shingles("we are urgently hiring a backend engineer to build scalable services")
    c = n.shingles("completely different text about frontend design systems and react")
    assert n.jaccard(a, a) == 1.0
    assert 0.3 < n.jaccard(a, b) < 1.0
    assert n.jaccard(a, c) == 0.0


def test_content_hash_is_order_independent_and_sensitive_to_values() -> None:
    h1 = n.content_hash({"a": 1, "b": "x"})
    assert h1 == n.content_hash({"b": "x", "a": 1})
    assert h1 != n.content_hash({"a": 2, "b": "x"})
    assert len(h1) == 64
