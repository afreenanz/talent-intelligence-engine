import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum_values
from app.db.enums import EmploymentType, LocationType, SkillSource
from app.domains.skills.models import Skill


class CandidateProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "candidate_profiles"
    __table_args__ = (
        CheckConstraint(
            "preferred_salary_min IS NULL OR preferred_salary_max IS NULL "
            "OR preferred_salary_min <= preferred_salary_max",
            name="salary_range_valid",
        ),
        CheckConstraint(
            "preferred_salary_min IS NULL OR preferred_salary_min >= 0", name="salary_min_nonneg"
        ),
        CheckConstraint(
            "experience_years IS NULL OR experience_years BETWEEN 0 AND 60",
            name="experience_years_range",
        ),
    )

    # unique=True makes this a strict one-to-one with users.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    full_name: Mapped[str | None] = mapped_column(Text)
    experience_years: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    # JSONB: always read/written whole, never filtered on. Shape enforced by Pydantic schemas.
    education: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    projects: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    location: Mapped[str | None] = mapped_column(Text)
    # Annual amounts in whole currency units (15 LPA = 1_500_000 INR).
    preferred_salary_min: Mapped[int | None] = mapped_column(BigInteger)
    preferred_salary_max: Mapped[int | None] = mapped_column(BigInteger)
    salary_currency: Mapped[str] = mapped_column(
        CHAR(3), nullable=False, server_default=text("'INR'")
    )
    preferred_job_type: Mapped[EmploymentType | None] = mapped_column(
        Enum(EmploymentType, name="employment_type", values_callable=pg_enum_values)
    )
    preferred_location_type: Mapped[LocationType | None] = mapped_column(
        Enum(LocationType, name="location_type", values_callable=pg_enum_values)
    )
    profile_summary: Mapped[str | None] = mapped_column(Text)

    skills: Mapped[list["CandidateSkill"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
        order_by="CandidateSkill.skill_id",
    )


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"
    __table_args__ = (
        CheckConstraint(
            "proficiency IS NULL OR proficiency BETWEEN 1 AND 5", name="proficiency_range"
        ),
        CheckConstraint(
            "experience_months IS NULL OR experience_months >= 0", name="experience_months_nonneg"
        ),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    # RESTRICT: a skill in use can't be deleted from the vocabulary by accident.
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    proficiency: Mapped[int | None] = mapped_column(SmallInteger)
    experience_months: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[SkillSource] = mapped_column(
        Enum(SkillSource, name="skill_source", values_callable=pg_enum_values),
        nullable=False,
        server_default=SkillSource.MANUAL.value,
    )

    candidate: Mapped[CandidateProfile] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship(lazy="joined")
