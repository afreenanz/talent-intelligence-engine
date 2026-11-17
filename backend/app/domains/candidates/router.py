from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.domains.candidates import service
from app.domains.candidates.schemas import ProfileOut, ProfileUpdate

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("/me", response_model=ProfileOut)
def get_me(user: CurrentUser, session: DbSession) -> ProfileOut:
    return service.to_profile_out(service.get_my_profile(session, user.id))


@router.put("/me", response_model=ProfileOut)
def update_me(body: ProfileUpdate, user: CurrentUser, session: DbSession) -> ProfileOut:
    return service.to_profile_out(service.update_my_profile(session, user.id, body))
