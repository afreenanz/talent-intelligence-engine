"""A ready-made demo account, so a visitor can see ranked matches without uploading a résumé.

The profile is fictional. The password never lives in code: it comes from DEMO_PASSWORD, or a
random one is generated and printed once.
"""

import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.domains.auth.models import User
from app.domains.auth.schemas import RegisterRequest
from app.domains.auth.service import register
from app.domains.candidates.schemas import ProfileUpdate
from app.domains.candidates.service import get_my_profile, update_my_profile
from app.domains.preferences.schemas import PreferenceKey
from app.domains.preferences.service import set_explicit

DEMO_EMAIL = "demo@example.com"

DEMO_PROFILE = ProfileUpdate.model_validate(
    {
        "full_name": "Demo Candidate",
        "experience_years": 3,
        "location": "Bengaluru",
        "profile_summary": "Backend engineer (fictional demo profile) building Python APIs.",
        "preferred_salary_min": 1_200_000,
        "skills": [
            {"name": n}
            for n in ["Python", "FastAPI", "PostgreSQL", "Docker", "SQL", "Redis", "Git"]
        ],
    }
)


def new_password() -> str:
    return secrets.token_urlsafe(12)


def seed_demo(session: Session, password: str) -> tuple[uuid.UUID, bool]:
    """Create the demo user (or reset its password and profile). Returns (user id, created)."""
    user = session.scalar(select(User).where(User.email == DEMO_EMAIL))
    created = user is None
    if user is None:
        user = register(
            session,
            RegisterRequest(email=DEMO_EMAIL, password=password, full_name="Demo Candidate"),
        )
    else:
        user.password_hash = security.hash_password(password)
        session.commit()
    update_my_profile(session, user.id, DEMO_PROFILE)
    profile = get_my_profile(session, user.id)
    set_explicit(
        session, profile.id, PreferenceKey.ROLE_CATEGORIES, {"prefer": ["backend"], "avoid": []}
    )
    session.commit()
    return user.id, created
