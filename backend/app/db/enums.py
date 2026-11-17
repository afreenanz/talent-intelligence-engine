"""Enums shared across domains (stored as PostgreSQL ENUM types)."""

from enum import StrEnum


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"


class LocationType(StrEnum):
    ONSITE = "onsite"
    REMOTE = "remote"
    HYBRID = "hybrid"


class SkillSource(StrEnum):
    MANUAL = "manual"
    RESUME = "resume"


class JobStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"  # expires_at has passed
    DUPLICATE = "duplicate"  # near-duplicate of another job (duplicate_of_job_id set)
    REMOVED = "removed"  # disappeared from a full-snapshot feed


class SkillImportance(StrEnum):
    REQUIRED = "required"  # listed by the source as required
    PREFERRED = "preferred"  # listed by the source as nice-to-have
    MENTIONED = "mentioned"  # found in the description text; importance unknown


class IngestionMode(StrEnum):
    INCREMENTAL = "incremental"  # upsert what is in the file; leave everything else alone
    SNAPSHOT = "snapshot"  # file is the full current feed; unseen active jobs become removed


class IngestionRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
