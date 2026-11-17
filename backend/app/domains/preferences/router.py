from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.domains.candidates import service as candidates
from app.domains.preferences import service
from app.domains.preferences.schemas import (
    PreferenceChange,
    PreferenceKey,
    PreferenceOut,
    PreferenceUpdate,
)

router = APIRouter(prefix="/candidates/me/preferences", tags=["preferences"])


@router.get("", response_model=list[PreferenceOut])
def list_preferences(user: CurrentUser, session: DbSession) -> list[PreferenceOut]:
    """Everything stored about your preferences: what you stated and (later) what was inferred."""
    cid = candidates.get_my_profile(session, user.id).id
    return [
        PreferenceOut(
            key=r.memory_key,
            value=r.memory_value,
            memory_type=r.memory_type,
            source=r.source,
            confidence=r.confidence,
            updated_at=r.updated_at,
        )
        for r in service.list_preferences(session, cid)
    ]


@router.put("/{key}", response_model=PreferenceChange)
def set_preference(
    key: PreferenceKey, body: PreferenceUpdate, user: CurrentUser, session: DbSession
) -> PreferenceChange:
    cid = candidates.get_my_profile(session, user.id).id
    return service.set_explicit(session, cid, key, body.value)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preference(key: PreferenceKey, user: CurrentUser, session: DbSession) -> None:
    cid = candidates.get_my_profile(session, user.id).id
    service.delete_explicit(session, cid, key)
