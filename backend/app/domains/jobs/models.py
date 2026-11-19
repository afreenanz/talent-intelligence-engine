import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum_values
from app.db.enums import EmploymentType, JobStatus, LocationType, SkillImportance
from app.domains.skills.models import Skill


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        # Hard identity: re-importing the same record from the same source is an update.
        UniqueConstraint("source", "external_id", name="uq_jobs_source_external_id"),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="salary_range_valid",
        ),
        CheckConstraint(
            "(salary_min IS NULL AND salary_max IS NULL) OR salary_currency IS NOT NULL",
            name="salary_has_currency",
        ),
        CheckConstraint(
            "experience_min IS NULL OR experience_max IS NULL OR experience_min <= experience_max",
            name="experience_range_valid",
        ),
        # A job is a duplicate exactly when it points at its canonical job.
        CheckConstraint(
            "(status = 'duplicate') = (duplicate_of_job_id IS NOT NULL)",
            name="duplicate_link_consistent",
        ),
        CheckConstraint("duplicate_of_job_id <> id", name="not_duplicate_of_self"),
        Index("ix_jobs_status_listed_at", "status", text("listed_at DESC"), "id"),
        # Soft identity lookup for near-duplicate detection.
        Index("ix_jobs_dedup_key", "normalized_company", "normalized_title"),
        Index("ix_jobs_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_jobs_active_expires_at",
            "expires_at",
            postgresql_where=text("status = 'active' AND expires_at IS NOT NULL"),
        ),
    )

    source: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_company: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    location: Mapped[str | None] = mapped_column(Text)  # as given by the source
    city: Mapped[str | None] = mapped_column(Text)  # canonical ("Bengaluru")
    country: Mapped[str | None] = mapped_column(Text)
    location_type: Mapped[LocationType | None] = mapped_column(
        Enum(LocationType, name="location_type", values_callable=pg_enum_values, create_type=False)
    )
    employment_type: Mapped[EmploymentType | None] = mapped_column(
        Enum(
            EmploymentType,
            name="employment_type",
            values_callable=pg_enum_values,
            create_type=False,
        )
    )

    # Annual, whole currency units (see database-design.md §3.8).
    salary_min: Mapped[int | None] = mapped_column(BigInteger)
    salary_max: Mapped[int | None] = mapped_column(BigInteger)
    salary_currency: Mapped[str | None] = mapped_column(CHAR(3))
    experience_min: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    experience_max: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", values_callable=pg_enum_values),
        nullable=False,
        server_default=JobStatus.ACTIVE.value,
    )
    duplicate_of_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL")
    )
    # SHA-256 of the normalized content. Unchanged hash = nothing to update or re-embed.
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)

    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # from source
    # Link to the original ad (feeds only). Shown as 'View original ad'; attribution needs it.
    apply_url: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Sort/recency key: posted_at when known, otherwise when we first saw the job. Kept separate
    # so we never invent a posted_at the source didn't give us.
    listed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Denormalised skill names, maintained by ingestion in the same transaction as job_skills.
    # Needed because a generated column can only read columns of its own row.
    skills_text: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    # Weighted full-text document, kept in sync by Postgres itself (GENERATED ... STORED).
    # Weights: A title, B skills, C company, D description.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english'::regconfig, coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english'::regconfig, coalesce(skills_text, '')), 'B') || "
            "setweight(to_tsvector('english'::regconfig, coalesce(company, '')), 'C') || "
            "setweight(to_tsvector('english'::regconfig, coalesce(description, '')), 'D')",
            persisted=True,
        ),
        nullable=False,
    )

    skills: Mapped[list["JobSkill"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="JobSkill.skill_id"
    )


class JobSkill(Base):
    __tablename__ = "job_skills"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    importance: Mapped[SkillImportance] = mapped_column(
        Enum(SkillImportance, name="skill_importance", values_callable=pg_enum_values),
        nullable=False,
    )

    job: Mapped[Job] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship(lazy="joined")
