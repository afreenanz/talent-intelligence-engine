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
