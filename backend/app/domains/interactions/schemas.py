import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import ApplicationStatus, InteractionType
from app.domains.jobs.schemas import JobSummary


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FeedbackIn(_Strict):
    job_id: uuid.UUID
    interaction_type: InteractionType = Field(description="click or dismiss")
    search_log_id: uuid.UUID | None = None
    position: int | None = Field(default=None, ge=1, le=1000)


class SaveJobIn(_Strict):
    job_id: uuid.UUID


class SavedJobOut(BaseModel):
    saved_at: datetime
    job: JobSummary


class SavedJobPage(BaseModel):
    items: list[SavedJobOut]
    next_cursor: str | None


class ApplyIn(_Strict):
    job_id: uuid.UUID
    notes: str | None = Field(default=None, max_length=2000)


class ApplicationUpdate(_Strict):
    application_status: ApplicationStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ApplicationOut(BaseModel):
    id: uuid.UUID
    application_status: ApplicationStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime
    job: JobSummary


class RecentSearchOut(BaseModel):
    id: uuid.UUID
    query: str | None
    filters: dict[str, object]
    result_count: int
    created_at: datetime
