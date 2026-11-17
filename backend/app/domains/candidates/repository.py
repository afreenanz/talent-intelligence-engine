import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domains.candidates.models import CandidateProfile, CandidateSkill


def get_profile_by_user_id(session: Session, user_id: uuid.UUID) -> CandidateProfile | None:
    """Profile + skills in 2 queries total (selectinload), regardless of skill count."""
    return session.scalar(
        select(CandidateProfile)
        .where(CandidateProfile.user_id == user_id)
        .options(selectinload(CandidateProfile.skills).joinedload(CandidateSkill.skill))
    )
