"""The fixed preference vocabulary (memory-design.md, rule 2).

Only these keys can be stored, each with its own validated value shape. Free-form "facts"
are not stored: they can't be validated, and the ranker can't use them.
"""

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.core.errors import ValidationFailedError
from app.db.enums import EmploymentType, LocationType, MemorySource, MemoryType


class RoleCategory(StrEnum):
    BACKEND = "backend"
    FRONTEND = "frontend"
    FULLSTACK = "fullstack"
    DATA = "data"
    ML = "ml"
    DEVOPS = "devops"
    MOBILE = "mobile"
    QA = "qa"
    SECURITY = "security"
    DESIGN = "design"
    PRODUCT = "product"


class _V(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoleCategoriesValue(_V):
    prefer: list[RoleCategory] = Field(default_factory=list, max_length=11)
    avoid: list[RoleCategory] = Field(default_factory=list, max_length=11)

    @model_validator(mode="after")
    def _disjoint(self) -> Self:
        both = set(self.prefer) & set(self.avoid)
        if both:
            raise ValueError(f"a category can't be both preferred and avoided: {sorted(both)}")
        if not self.prefer and not self.avoid:
            raise ValueError("provide at least one category to prefer or avoid")
        return self


class LocationsValue(_V):
    cities: list[str] = Field(min_length=1, max_length=10)


class LocationTypeValue(_V):
    value: LocationType


class MinSalaryValue(_V):
    amount: int = Field(gt=0, le=10**10, description="annual, whole currency units")
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")


class EmploymentTypeValue(_V):
    value: EmploymentType


class CompanyAvoidValue(_V):
    companies: list[str] = Field(min_length=1, max_length=50)


class SkillsToUseValue(_V):
    skills: list[str] = Field(min_length=1, max_length=30)


class PreferenceKey(StrEnum):
    ROLE_CATEGORIES = "role_categories"
    LOCATIONS = "locations"
    LOCATION_TYPE = "location_type"
    MIN_SALARY = "min_salary"
    EMPLOYMENT_TYPE = "employment_type"
    COMPANY_AVOID = "company_avoid"
    SKILLS_TO_USE = "skills_to_use"


VALUE_SCHEMAS: dict[PreferenceKey, type[_V]] = {
    PreferenceKey.ROLE_CATEGORIES: RoleCategoriesValue,
    PreferenceKey.LOCATIONS: LocationsValue,
    PreferenceKey.LOCATION_TYPE: LocationTypeValue,
    PreferenceKey.MIN_SALARY: MinSalaryValue,
    PreferenceKey.EMPLOYMENT_TYPE: EmploymentTypeValue,
    PreferenceKey.COMPANY_AVOID: CompanyAvoidValue,
    PreferenceKey.SKILLS_TO_USE: SkillsToUseValue,
}


def validate_value(key: PreferenceKey, value: dict[str, Any]) -> dict[str, Any]:
    """Validate against the key's schema; returns the normalised JSON-ready value."""
    try:
        return VALUE_SCHEMAS[key].model_validate(value).model_dump(mode="json")
    except ValidationError as exc:
        details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        raise ValidationFailedError(
            f"Invalid value for preference {key.value!r}", details=details
        ) from exc


class PreferenceOut(BaseModel):
    key: str
    value: dict[str, Any]
    memory_type: MemoryType
    source: MemorySource
    confidence: float
    updated_at: Any


class PreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: dict[str, Any]


class PreferenceChange(BaseModel):
    """Returned on every write, so a caller (e.g. the agent) can say "changed from X to Y"."""

    key: str
    value: dict[str, Any]
    previous: dict[str, Any] | None
    created: bool
