"""Candidate profile use cases.

Ownership rule: every function takes the *authenticated* user_id (from the access token) and
looks the profile up by it. No endpoint accepts a profile or user id from the client, so one
candidate can't address another candidate's profile at all.
"""

import uuid

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.enums import SkillSource
from app.domains.candidates import repository
from app.domains.candidates.models import CandidateProfile, CandidateSkill
from app.domains.candidates.schemas import CandidateSkillOut, ProfileOut, ProfileUpdate
from app.domains.skills.normalization import normalize_skill_name
from app.domains.skills.repository import resolve_or_create_skills


def get_my_profile(session: Session, user_id: uuid.UUID) -> CandidateProfile:
    profile = repository.get_profile_by_user_id(session, user_id)
    if profile is None:
        raise NotFoundError("Candidate profile not found")
    return profile


def update_my_profile(
    session: Session, user_id: uuid.UUID, data: ProfileUpdate
) -> CandidateProfile:
    profile = get_my_profile(session, user_id)

    profile.full_name = data.full_name
    profile.experience_years = data.experience_years
    profile.education = [e.model_dump(mode="json") for e in data.education]
    profile.projects = [p.model_dump(mode="json") for p in data.projects]
    profile.location = data.location
    profile.preferred_salary_min = data.preferred_salary_min
    profile.preferred_salary_max = data.preferred_salary_max
    profile.salary_currency = data.salary_currency
    profile.preferred_job_type = data.preferred_job_type
    profile.preferred_location_type = data.preferred_location_type
    profile.profile_summary = data.profile_summary

    _replace_skills(session, profile, data)
    session.commit()
    # Reload so the response reflects exactly what the database now holds.
    session.expire_all()
    return get_my_profile(session, user_id)


def _replace_skills(session: Session, profile: CandidateProfile, data: ProfileUpdate) -> None:
    """Diff the submitted skill list against stored skills: update, insert, delete."""
    skills_by_norm = resolve_or_create_skills(session, (s.name for s in data.skills))
    wanted = {skills_by_norm[normalize_skill_name(s.name)].id: s for s in data.skills}
    existing = {cs.skill_id: cs for cs in profile.skills}

    for skill_id, cs in existing.items():
        if skill_id not in wanted:
            profile.skills.remove(cs)  # delete-orphan cascade removes the row

    for skill_id, item in wanted.items():
        if skill_id in existing:
            cs = existing[skill_id]
            cs.proficiency = item.proficiency
            cs.experience_months = item.experience_months
            # `source` is kept: a resume-derived skill stays marked as such when edited.
        else:
            profile.skills.append(
                CandidateSkill(
                    skill_id=skill_id,
                    proficiency=item.proficiency,
                    experience_months=item.experience_months,
                    source=SkillSource.MANUAL,
                )
            )


def to_profile_out(profile: CandidateProfile) -> ProfileOut:
    skills = [
        CandidateSkillOut(
            skill_id=cs.skill_id,
            name=cs.skill.name,
            normalized_name=cs.skill.normalized_name,
            proficiency=cs.proficiency,
            experience_months=cs.experience_months,
            source=cs.source,
        )
        for cs in profile.skills
    ]
    return ProfileOut.model_validate(
        {
            **{k: getattr(profile, k) for k in ProfileOut.model_fields if k != "skills"},
            "skills": skills,
        }
    )
