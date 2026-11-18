"""Resume endpoints.

Processing runs in the Celery worker (one LLM call takes ~10-15 s); the API only enqueues.
That is an interim choice: Milestone 9 moves it to a Celery worker, so work survives API
restarts and can be retried by a queue. The processor is a dependency so tests can run it
against the test transaction.
"""

import uuid
from collections.abc import Callable
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.deps import CurrentUser, DbSession, SettingsDep
from app.core.errors import UpstreamUnavailableError
from app.core.rate_limit import RESUME, by_user
from app.domains.candidates import service as candidates
from app.domains.candidates.schemas import ProfileOut
from app.domains.resumes import service
from app.domains.resumes.models import Resume
from app.domains.resumes.schemas import ResumeApplyRequest, ResumeOut
from app.integrations.llm.base import LLMUnavailableError
from app.integrations.llm.factory import get_llm_provider

router = APIRouter(prefix="/candidates", tags=["resumes"])

log = structlog.get_logger()

ResumeProcessor = Callable[[uuid.UUID], None]


def get_resume_processor() -> ResumeProcessor:
    """Fail fast with 503 if no LLM is configured, before anything is stored."""
    try:
        get_llm_provider()  # only checks one is configured; the worker builds its own
    except LLMUnavailableError as exc:
        raise UpstreamUnavailableError(
            "Resume extraction is unavailable: no LLM provider is configured"
        ) from exc

    def enqueue(resume_id: uuid.UUID) -> None:
        # Hand off to the Celery worker. If the broker is down, the resume stays 'pending' and
        # the periodic requeue task picks it up later, so the upload itself still succeeds.
        from app.worker.tasks import process_resume

        try:
            process_resume.delay(str(resume_id))
        except Exception as exc:
            log.error("resume_enqueue_failed", resume_id=str(resume_id), error=str(exc))

    return enqueue


Processor = Annotated[ResumeProcessor, Depends(get_resume_processor)]


def _out(resume: Resume) -> ResumeOut:
    return ResumeOut.model_validate(
        {
            **{k: getattr(resume, k) for k in ResumeOut.model_fields if k != "parsed_data"},
            "parsed_data": service.parsed_view(resume),
        }
    )


@router.post(
    "/resume",
    response_model=ResumeOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(by_user(RESUME))],
)
def upload_resume(
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
    processor: Processor,
    file: Annotated[UploadFile, File(description="PDF resume, max 5 MB")],
) -> ResumeOut:
    # Read at most limit+1 bytes: enough to detect "too large" without buffering a huge upload.
    data = file.file.read(settings.max_resume_bytes + 1)
    resume = service.upload_resume(session, user.id, file.filename, data, settings)
    processor(resume.id)
    return _out(resume)


@router.get("/resumes", response_model=list[ResumeOut])
def list_resumes(user: CurrentUser, session: DbSession) -> list[ResumeOut]:
    return [_out(r) for r in service.list_my_resumes(session, user.id)]


@router.get("/resumes/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: uuid.UUID, user: CurrentUser, session: DbSession) -> ResumeOut:
    return _out(service.get_my_resume(session, user.id, resume_id))


@router.post(
    "/resumes/{resume_id}/reprocess",
    response_model=ResumeOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(by_user(RESUME))],
)
def reprocess_resume(
    resume_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    processor: Processor,
) -> ResumeOut:
    resume = service.reprocess_my_resume(session, user.id, resume_id)
    processor(resume.id)
    return _out(resume)


@router.post("/resumes/{resume_id}/apply", response_model=ProfileOut)
def apply_resume(
    resume_id: uuid.UUID, body: ResumeApplyRequest, user: CurrentUser, session: DbSession
) -> ProfileOut:
    profile = service.apply_to_profile(session, user.id, resume_id, body)
    return candidates.to_profile_out(profile)


@router.delete("/resumes/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(resume_id: uuid.UUID, user: CurrentUser, session: DbSession) -> None:
    service.delete_my_resume(session, user.id, resume_id)
