"""Pure normalization functions: raw job fields to canonical internal values.

No database access and no I/O, so every rule here is unit-tested in isolation. The rule
throughout: when a value can't be parsed with confidence, return None and record a warning.
Never guess.
"""

import hashlib
import html
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from html.parser import HTMLParser

from app.db.enums import LocationType

# ---------------------------------------------------------------- text / description


class _TextExtractor(HTMLParser):
    _BLOCK = frozenset(
        {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "tr", "section"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._BLOCK:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


_SPACES = re.compile(r"[ \t\u00a0]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")
MAX_DESCRIPTION_CHARS = 20_000


def clean_description(raw: str) -> str:
    """Strip HTML, unescape entities, normalise whitespace; keep paragraph breaks."""
    if "<" in raw and ">" in raw:
        parser = _TextExtractor()
        parser.feed(raw)
        parser.close()
        text = "".join(parser.parts)
    else:
        text = html.unescape(raw)
    lines = [_SPACES.sub(" ", line).strip() for line in text.replace("\r", "\n").split("\n")]
    text = _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
    return text[:MAX_DESCRIPTION_CHARS]


# ---------------------------------------------------------------- titles and companies

_NON_ALNUM = re.compile(r"[^a-z0-9+#.\s]")
_TITLE_ABBREVIATIONS = {
    "sr": "senior",
    "jr": "junior",
    "snr": "senior",
    "swe": "software engineer",
    "sde": "software development engineer",
    "eng": "engineer",
    "engg": "engineer",
    "dev": "developer",
    "mgr": "manager",
    "ml": "machine learning",
    "ai": "ai",
    "qa": "quality assurance",
}
_COMPANY_SUFFIXES = re.compile(
    r"\b(private limited|pvt\.? ltd\.?|pvt|ltd\.?|limited|inc\.?|llc|llp|corp\.?|"
    r"corporation|co\.?|gmbh|plc)$"
)


def normalize_title(title: str) -> str:
    """Dedup key for titles. Keeps seniority: 'Senior X' and 'Junior X' are different jobs."""
    text = _NON_ALNUM.sub(" ", title.lower())
    words = [_TITLE_ABBREVIATIONS.get(w.strip("."), w.strip(".")) for w in text.split()]
    return " ".join(w for w in words if w)


def normalize_company(company: str) -> str:
    text = re.sub(r"[,()]", " ", company.lower())
    text = _SPACES.sub(" ", text).strip()
    previous = None
    while (
        previous != text
    ):  # strip stacked suffixes: "Foo Technologies Pvt Ltd" -> "foo technologies"
        previous = text
        text = _COMPANY_SUFFIXES.sub("", text).strip(" .,")
    return text


# ---------------------------------------------------------------- location


_CITY_ALIASES: dict[str, tuple[str, str]] = {
    "bangalore": ("Bengaluru", "India"),
    "bengaluru": ("Bengaluru", "India"),
    "mumbai": ("Mumbai", "India"),
    "bombay": ("Mumbai", "India"),
    "navi mumbai": ("Navi Mumbai", "India"),
    "delhi": ("Delhi", "India"),
    "new delhi": ("Delhi", "India"),
    "gurgaon": ("Gurugram", "India"),
    "gurugram": ("Gurugram", "India"),
    "noida": ("Noida", "India"),
    "hyderabad": ("Hyderabad", "India"),
    "chennai": ("Chennai", "India"),
    "madras": ("Chennai", "India"),
    "pune": ("Pune", "India"),
    "kolkata": ("Kolkata", "India"),
    "calcutta": ("Kolkata", "India"),
    "ahmedabad": ("Ahmedabad", "India"),
    "kochi": ("Kochi", "India"),
    "cochin": ("Kochi", "India"),
    "jaipur": ("Jaipur", "India"),
    "chandigarh": ("Chandigarh", "India"),
    "coimbatore": ("Coimbatore", "India"),
    "thiruvananthapuram": ("Thiruvananthapuram", "India"),
    "trivandrum": ("Thiruvananthapuram", "India"),
    "singapore": ("Singapore", "Singapore"),
    "london": ("London", "United Kingdom"),
    "berlin": ("Berlin", "Germany"),
    "dubai": ("Dubai", "United Arab Emirates"),
    "san francisco": ("San Francisco", "United States"),
    "new york": ("New York", "United States"),
    "seattle": ("Seattle", "United States"),
    "toronto": ("Toronto", "Canada"),
}
_COUNTRIES = {
    "india": "India",
    "usa": "United States",
    "us": "United States",
    "united states": "United States",
    "uk": "United Kingdom",
    "united kingdom": "United Kingdom",
    "germany": "Germany",
    "singapore": "Singapore",
    "canada": "Canada",
    "uae": "United Arab Emirates",
}


@dataclass(frozen=True)
class ParsedLocation:
    city: str | None
    country: str | None
    location_type: LocationType | None


def parse_location(raw: str | None) -> ParsedLocation:
    """'Bangalore, Karnataka, India' / 'Remote (India)' / 'Hybrid - Pune' -> canonical parts."""
    if not raw or not raw.strip():
        return ParsedLocation(None, None, None)
    text = raw.lower()
    loc_type: LocationType | None = None
    if re.search(r"\bremote\b|\bwfh\b|work from home", text):
        loc_type = LocationType.REMOTE
    if re.search(r"\bhybrid\b", text):
        loc_type = LocationType.HYBRID
    if re.search(r"\bon-?site\b|\bin-?office\b", text):
        loc_type = LocationType.ONSITE

    parts = [p.strip() for p in re.split(r"[,/()\-|]", text) if p.strip()]
    city = country = None
    for part in parts:
        cleaned = re.sub(r"\b(remote|hybrid|on-?site|wfh)\b", "", part).strip()
        if not cleaned:
            continue
        if city is None and cleaned in _CITY_ALIASES:
            city, country = _CITY_ALIASES[cleaned]
        elif cleaned in _COUNTRIES:
            country = _COUNTRIES[cleaned]
    return ParsedLocation(city, country, loc_type)


# ---------------------------------------------------------------- salary


@dataclass(frozen=True)
class ParsedSalary:
    minimum: int | None
    maximum: int | None
    currency: str | None


_CURRENCY_MARKERS = [
    (re.compile(r"₹|\binr\b|\brs\.?\s|\brupees?\b|\blpa\b|\blakhs?\b|\bcr\b|\bcrores?\b"), "INR"),
    (re.compile(r"\$|\busd\b"), "USD"),
    (re.compile(r"€|\beur\b"), "EUR"),
    (re.compile(r"£|\bgbp\b"), "GBP"),
    (re.compile(r"\bsgd\b|s\$"), "SGD"),
]
_NUMBER = re.compile(r"(\d+(?:\.\d+)?)\s*(k|lpa|lakhs?|l|cr|crores?|m)?\b")
_PERIOD_MULTIPLIERS = [
    (re.compile(r"per\s*hour|/\s*h(ou)?r|\bhourly\b|\bph\b"), 2080),  # 40h x 52w
    (re.compile(r"per\s*month|/\s*mo(nth)?|\bmonthly\b|\bpm\b|p\.m\."), 12),
]
_UNIT_MULTIPLIERS = {
    "k": 1_000,
    "l": 100_000,
    "lpa": 100_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "cr": 10_000_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "m": 1_000_000,
}
PERIOD_TO_ANNUAL = {"annual": 1, "yearly": 1, "monthly": 12, "hourly": 2080}


def parse_salary_text(raw: str | None, default_currency: str | None = None) -> ParsedSalary:
    """Parse '15-25 LPA', '₹8,00,000 - ₹12,00,000 p.a.', '$120k-$150k', '50,000/month'.

    Returns annual amounts. Unparseable or inverted ranges give an empty ParsedSalary.
    """
    empty = ParsedSalary(None, None, None)
    if not raw or not raw.strip():
        return empty
    text = raw.lower().replace(",", "")
    currency = next((code for rx, code in _CURRENCY_MARKERS if rx.search(text)), default_currency)
    period = next((mult for rx, mult in _PERIOD_MULTIPLIERS if rx.search(text)), 1)

    matches = _NUMBER.findall(text)
    if not matches or currency is None:
        return empty
    # A unit written once applies to both ends: "15-25 LPA" means 15 LPA - 25 LPA.
    units = [u for _, u in matches if u]
    shared_unit = units[-1] if units else ""
    values = []
    for number, unit in matches[:2]:
        multiplier = _UNIT_MULTIPLIERS.get(unit or shared_unit, 1)
        values.append(int(Decimal(number) * multiplier * period))
    lo, hi = (values[0], values[-1])
    if lo > hi or lo <= 0:
        return empty
    return ParsedSalary(lo, hi, currency)


def annualize(amount: int | float | None, period: str) -> int | None:
    if amount is None:
        return None
    return int(Decimal(str(amount)) * PERIOD_TO_ANNUAL[period])


# ---------------------------------------------------------------- experience


def parse_experience_text(raw: str | None) -> tuple[Decimal | None, Decimal | None]:
    """'2-5 years' -> (2, 5); '3+ yrs' -> (3, None); 'fresher' -> (0, 1)."""
    if not raw or not raw.strip():
        return None, None
    text = raw.lower()
    if re.search(r"\bfresher|\bentry[- ]level|\bno experience", text):
        return Decimal(0), Decimal(1)
    nums = [Decimal(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]
    if not nums or any(n > 60 for n in nums):
        return None, None
    if len(nums) >= 2:
        lo, hi = nums[0], nums[1]
        return (lo, hi) if lo <= hi else (None, None)
    if "+" in text or "at least" in text or "minimum" in text or "min" in text:
        return nums[0], None
    return nums[0], nums[0]


# ---------------------------------------------------------------- similarity and hashing


def shingles(text: str, k: int = 5) -> set[str]:
    """Word k-gram shingles over lowercased alphanumeric tokens."""
    tokens = re.findall(r"[a-z0-9+#]+", text.lower())
    if len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


@dataclass
class NormalizationWarnings:
    messages: list[str] = field(default_factory=list)

    def add(self, msg: str) -> None:
        self.messages.append(msg)


def content_hash(fields: dict[str, object]) -> str:
    """Stable SHA-256 over normalized fields (sorted keys, canonical JSON)."""
    payload = json.dumps(fields, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
