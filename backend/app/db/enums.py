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


class ResumeStatus(StrEnum):
    PENDING = "pending"  # uploaded, waiting for processing
    PROCESSING = "processing"
    PARSED = "parsed"  # extraction ready for the candidate to review
    FAILED = "failed"  # see parsing_error; can be reprocessed
    REVIEWED = "reviewed"  # candidate confirmed it and it was applied to the profile


class InteractionType(StrEnum):
    IMPRESSION = "impression"  # shown in a result list (logged by the server)
    CLICK = "click"  # opened the job
    SAVE = "save"
    UNSAVE = "unsave"
    DISMISS = "dismiss"  # "not interested"
    APPLY = "apply"


class ApplicationStatus(StrEnum):
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class MemoryType(StrEnum):
    EXPLICIT_PREFERENCE = "explicit_preference"  # stated by the candidate (settings or agent)
    DERIVED_PREFERENCE = "derived_preference"  # inferred from behaviour (Milestone 5B)


class MemorySource(StrEnum):
    SETTINGS = "settings"
    AGENT = "agent"
    DERIVED = "derived"
