import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Environment, Settings
from app.domains.candidates.schemas import EducationItem, ProfileUpdate
from app.domains.skills.normalization import normalize_skill_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Python", "python"),
        ("  PostgreSQL  ", "postgresql"),
        ("Machine   Learning", "machine learning"),
        ("C++", "c++"),
        ("C#", "c#"),
        (".NET", ".net"),
        ("Node.js", "node.js"),
        ("\uff30\uff59\uff54\uff48\uff4f\uff4e", "python"),  # full-width "Python" -> NFKC
        ("   ", ""),
    ],
)
def test_normalize_skill_name(raw: str, expected: str) -> None:
    assert normalize_skill_name(raw) == expected


def test_profile_rejects_inverted_salary_range() -> None:
    with pytest.raises(ValidationError, match="preferred_salary_min must be <="):
        ProfileUpdate(preferred_salary_min=20, preferred_salary_max=10)


def test_profile_rejects_duplicate_skills_after_normalization() -> None:
    with pytest.raises(ValidationError, match="duplicate skill"):
        ProfileUpdate(skills=[{"name": "Python"}, {"name": "  python "}])  # type: ignore[list-item]


def test_profile_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ProfileUpdate.model_validate({"user_id": "00000000-0000-0000-0000-000000000000"})


def test_education_years_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="end_year"):
        EducationItem(institution="X", start_year=2024, end_year=2020)


def test_production_refuses_default_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    # Isolate from the developer's .env and environment, which may hold a real secret.
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(environment=Environment.PRODUCTION, _env_file=None)  # type: ignore[call-arg]


def test_short_jwt_secret_rejected_in_any_environment() -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(environment=Environment.DEVELOPMENT, jwt_secret=SecretStr(""))


def test_production_accepts_strong_secret() -> None:
    s = Settings(environment=Environment.PRODUCTION, jwt_secret=SecretStr("z" * 48))
    assert s.environment is Environment.PRODUCTION
