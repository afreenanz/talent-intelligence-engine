"""The external job record contract: what a CSV row / JSON object must look like.

Two ways to give salary and experience, because real feeds do both:
- structured: salary_min / salary_max / salary_currency / salary_period, experience_min / max
- text: salary_text ("15-25 LPA"), experience_text ("2-5 years")
Structured fields win when both are present.
"""

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.enums import EmploymentType, LocationType

_EMPLOYMENT_ALIASES = {
    "full-time": "full_time",
    "full time": "full_time",
    "fulltime": "full_time",
    "permanent": "full_time",
    "part-time": "part_time",
    "part time": "part_time",
    "contractor": "contract",
    "freelance": "contract",
    "intern": "internship",
    "temp": "temporary",
}


def _split_list(value: object) -> object:
    """CSV cells hold lists as 'Python; FastAPI | SQL'. JSON already gives a list."""
    if isinstance(value, str):
        return [part.strip() for part in value.replace("|", ";").split(";") if part.strip()]
    return value


class JobRecordIn(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    external_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=2, max_length=300)
    company: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=20, max_length=100_000)
    location: str | None = Field(default=None, max_length=300)
    location_type: LocationType | None = None
    employment_type: EmploymentType | None = None

    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")
    salary_period: Literal["annual", "yearly", "monthly", "hourly"] = "annual"
    salary_text: str | None = Field(default=None, max_length=200)

    experience_min: float | None = Field(default=None, ge=0, le=60)
    experience_max: float | None = Field(default=None, ge=0, le=60)
    experience_text: str | None = Field(default=None, max_length=200)

    required_skills: list[str] = Field(default_factory=list, max_length=60)
    preferred_skills: list[str] = Field(default_factory=list, max_length=60)

    posted_at: datetime | None = None
    expires_at: datetime | None = None

    @field_validator("required_skills", "preferred_skills", mode="before")
    @classmethod
    def _lists(cls, v: object) -> object:
        return [] if v is None else _split_list(v)

    @field_validator(
        "location",
        "location_type",
        "employment_type",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_text",
        "experience_min",
        "experience_max",
        "experience_text",
        "posted_at",
        "expires_at",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, v: object) -> object:
        # CSV has no null: an empty cell arrives as "".
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("employment_type", mode="before")
    @classmethod
    def _employment_aliases(cls, v: object) -> object:
        if isinstance(v, str):
            key = v.strip().lower()
            return _EMPLOYMENT_ALIASES.get(key, key.replace("-", "_").replace(" ", "_"))
        return v

    @field_validator("location_type", "salary_period", mode="before")
    @classmethod
    def _lower(cls, v: object) -> object:
        return v.strip().lower().replace("-", "") if isinstance(v, str) else v

    @field_validator("posted_at", "expires_at")
    @classmethod
    def _assume_utc(cls, v: datetime | None) -> datetime | None:
        # A naive timestamp is interpreted as UTC (documented) rather than server-local time.
        return v.replace(tzinfo=UTC) if v is not None and v.tzinfo is None else v

    @model_validator(mode="after")
    def _ranges(self) -> Self:
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("salary_min must be <= salary_max")
        if (
            self.salary_min is not None or self.salary_max is not None
        ) and not self.salary_currency:
            raise ValueError("salary_currency is required when salary_min/max are given")
        if (
            self.experience_min is not None
            and self.experience_max is not None
            and self.experience_min > self.experience_max
        ):
            raise ValueError("experience_min must be <= experience_max")
        if self.posted_at and self.expires_at and self.expires_at < self.posted_at:
            raise ValueError("expires_at must be after posted_at")
        return self
