import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbSession
from app.domains.candidates import service as candidates
from app.domains.interactions import service
from app.domains.interactions.models import Application
from app.domains.interactions.schemas import (
    ApplicationOut,
    ApplicationUpdate,
    ApplyIn,
    FeedbackIn,
    RecentSearchOut,
    SavedJobOut,
    SavedJobPage,
    SaveJobIn,
)
from app.domains.jobs.models import Job
from app.domains.jobs.schemas import JobSummary

router = APIRouter()


def _cid(session: DbSession, user: CurrentUser) -> uuid.UUID:
    return candidates.get_my_profile(session, user.id).id


def _summary(job: Job) -> JobSummary:
    return JobSummary.model_validate({k: getattr(job, k) for k in JobSummary.model_fields})


def _app_out(a: Application, job: Job) -> ApplicationOut:
    return ApplicationOut(
        id=a.id,
        application_status=a.application_status,
        notes=a.notes,
        created_at=a.created_at,
        updated_at=a.updated_at,
        job=_summary(job),
    )


@router.post(
    "/recommendations/feedback", status_code=status.HTTP_201_CREATED, tags=["recommendations"]
)
def feedback(body: FeedbackIn, user: CurrentUser, session: DbSession) -> dict[str, str]:
    """Record a click or a dismissal ("not interested").

    Saves and applications have their own endpoints."""
    service.record_feedback(
        session,
        _cid(session, user),
        body.job_id,
        body.interaction_type,
        body.search_log_id,
        body.position,
    )
    return {"status": "recorded"}


@router.get("/candidates/me/searches", response_model=list[RecentSearchOut], tags=["candidates"])
def recent_searches(
    user: CurrentUser, session: DbSession, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> list[RecentSearchOut]:
    return [
        RecentSearchOut.model_validate(s, from_attributes=True)
        for s in service.recent_searches(session, _cid(session, user), limit)
    ]


@router.post("/saved-jobs", status_code=status.HTTP_201_CREATED, tags=["saved-jobs"])
def save(
    body: SaveJobIn, user: CurrentUser, session: DbSession, response: Response
) -> dict[str, object]:
    created = service.save_job(session, _cid(session, user), body.job_id)
    if not created:
        response.status_code = status.HTTP_200_OK  # already saved: idempotent
    return {"job_id": str(body.job_id), "saved": True, "created": created}


@router.get("/saved-jobs", response_model=SavedJobPage, tags=["saved-jobs"])
def list_saved(
    user: CurrentUser,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> SavedJobPage:
    rows, nxt = service.list_saved(session, _cid(session, user), limit, cursor)
    return SavedJobPage(
        items=[SavedJobOut(saved_at=s.created_at, job=_summary(j)) for s, j in rows],
        next_cursor=nxt,
    )


@router.delete("/saved-jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["saved-jobs"])
def unsave(job_id: uuid.UUID, user: CurrentUser, session: DbSession) -> None:
    service.unsave_job(session, _cid(session, user), job_id)


@router.post(
    "/applications",
    response_model=ApplicationOut,
    status_code=status.HTTP_201_CREATED,
    tags=["applications"],
)
def apply(body: ApplyIn, user: CurrentUser, session: DbSession) -> ApplicationOut:
    a = service.apply(session, _cid(session, user), body.job_id, body.notes)
    return _app_out(a, session.get(Job, a.job_id))  # type: ignore[arg-type]


@router.get("/applications", response_model=list[ApplicationOut], tags=["applications"])
def list_applications(user: CurrentUser, session: DbSession) -> list[ApplicationOut]:
    return [_app_out(a, j) for a, j in service.list_applications(session, _cid(session, user))]


@router.patch(
    "/applications/{application_id}", response_model=ApplicationOut, tags=["applications"]
)
def update_application(
    application_id: uuid.UUID, body: ApplicationUpdate, user: CurrentUser, session: DbSession
) -> ApplicationOut:
    a = service.update_application(
        session, _cid(session, user), application_id, body.application_status, body.notes
    )
    return _app_out(a, session.get(Job, a.job_id))  # type: ignore[arg-type]
