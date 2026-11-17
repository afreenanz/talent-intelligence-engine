"""Resume use cases: upload → process (text → LLM → checks) → review → apply to profile.

Ownership: every query is scoped to the authenticated user's candidate profile. A resume ID
belonging to someone else returns 404 (not 403), so IDs can't be probed for existence.
"""

import hashlib
import os
import re
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.enums import ResumeStatus, SkillSource
from app.domains.candidates import service as candidates
from app.domains.candidates.models import CandidateProfile, CandidateSkill
from app.domains.resumes import postprocess
from app.domains.resumes.models import Resume
from app.domains.resumes.pdf_text import ResumeTextError, extract_text, looks_like_pdf
from app.domains.resumes.prompts import RESUME_EXTRACTION_VERSION, build_resume_prompt
from app.domains.resumes.schemas import ParsedResume, ResumeApplyRequest, ResumeExtraction
from app.domains.skills.extraction import build_matcher
from app.domains.skills.models import Skill
from app.domains.skills.normalization import normalize_skill_name
from app.domains.skills.repository import lookup_skills, resolve_or_create_skills
from app.integrations.llm.base import LLMProvider, LLMResponseError, LLMUnavailableError

log = structlog.get_logger(__name__)

_UNSAFE_FILENAME = re.compile(r"[^\w.\- ]+")


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class UnsupportedMediaError(AppError):
    status_code = 415
    code = "unsupported_media_type"


def _safe_display_name(filename: str | None) -> str:
    base = os.path.basename(filename or "resume.pdf")
    return (_UNSAFE_FILENAME.sub("_", base).strip() or "resume.pdf")[:255]


# ---------------------------------------------------------------- upload


def upload_resume(
    session: Session, user_id: uuid.UUID, filename: str | None, data: bytes, settings: Settings
) -> Resume:
    if len(data) > settings.max_resume_bytes:
        raise PayloadTooLargeError(f"Resume must be at most {settings.max_resume_bytes} bytes")
    if not data or not looks_like_pdf(data):
        raise UnsupportedMediaError("Only PDF resumes are supported")

    profile = candidates.get_my_profile(session, user_id)
    resume_id = uuid.uuid4()
    # The path is built only from server-generated UUIDs; the user's filename is display-only.
    directory = Path(settings.upload_dir) / str(profile.id)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"{resume_id}.pdf"
    path.write_bytes(data)
    os.chmod(path, 0o600)

    resume = Resume(
        id=resume_id,
        candidate_id=profile.id,
        file_path=str(path),
        original_filename=_safe_display_name(filename),
        file_sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        parsing_status=ResumeStatus.PENDING,
    )
    session.add(resume)
    try:
        session.commit()
    except Exception:
        path.unlink(missing_ok=True)  # don't leave orphan files behind
        raise
    log.info("resume_uploaded", resume_id=str(resume.id), size=len(data))
    return resume


# ---------------------------------------------------------------- processing


def process_resume(
    session: Session, resume_id: uuid.UUID, llm: LLMProvider, today: date | None = None
) -> ResumeStatus:
    """Run the pipeline for one resume. Safe to call twice: only one caller can claim it."""
    claimed = session.execute(
        update(Resume)
        .where(
            Resume.id == resume_id,
            Resume.parsing_status.in_([ResumeStatus.PENDING, ResumeStatus.FAILED]),
        )
        .values(parsing_status=ResumeStatus.PROCESSING, parsing_error=None)
        .returning(Resume.id)
    ).first()
    session.commit()
    if claimed is None:
        log.info("resume_not_claimable", resume_id=str(resume_id))
        current = session.scalar(select(Resume.parsing_status).where(Resume.id == resume_id))
        return current or ResumeStatus.FAILED

    resume = session.get(Resume, resume_id)
    assert resume is not None  # noqa: S101 (just claimed it)
    try:
        extracted = extract_text(Path(resume.file_path).read_bytes())
        resume.page_count = extracted.page_count
        resume.extracted_text = extracted.text

        result = llm.generate_structured(build_resume_prompt(extracted.text), ResumeExtraction)
        resume.llm_model = result.usage.model
        resume.llm_latency_ms = result.usage.latency_ms
        resume.llm_input_tokens = result.usage.input_tokens
        resume.llm_output_tokens = result.usage.output_tokens

        matcher = build_matcher(session)
        found_ids = matcher.find(extracted.text)
        dictionary = dict(
            session.execute(select(Skill.id, Skill.name).where(Skill.id.in_(found_ids))).all()
        )
        parsed = postprocess.postprocess(
            result.value,
            extracted.text,
            resolve_skills=lambda names: lookup_skills(session, names),
            dictionary_skills=dictionary,
            today=today or datetime.now(UTC).date(),
            prompt_version=RESUME_EXTRACTION_VERSION,
            text_truncated=extracted.truncated,
        )
        resume.parsed_data = parsed.model_dump(mode="json")
        resume.parsing_status = ResumeStatus.PARSED
    except ResumeTextError as exc:
        _fail(resume, str(exc))
    except FileNotFoundError:
        _fail(resume, "The uploaded file is missing from storage. Please upload it again.")
    except LLMUnavailableError as exc:
        _fail(resume, "The extraction service is temporarily unavailable. Try again later.")
        log.warning("resume_llm_unavailable", resume_id=str(resume_id), error=str(exc))
    except LLMResponseError as exc:
        _fail(resume, "The extraction service returned an unusable answer. Try again later.")
        log.warning("resume_llm_bad_response", resume_id=str(resume_id), error=str(exc))
    session.commit()
    log.info(
        "resume_processed",
        resume_id=str(resume_id),
        status=resume.parsing_status.value,
        latency_ms=resume.llm_latency_ms,
    )
    return resume.parsing_status


def _fail(resume: Resume, message: str) -> None:
    resume.parsing_status = ResumeStatus.FAILED
    resume.parsing_error = message


# ---------------------------------------------------------------- read / delete


def list_my_resumes(session: Session, user_id: uuid.UUID) -> list[Resume]:
    profile = candidates.get_my_profile(session, user_id)
    return list(
        session.scalars(
            select(Resume)
            .where(Resume.candidate_id == profile.id)
            .order_by(Resume.created_at.desc())
        )
    )


def get_my_resume(session: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    resume = session.scalar(
        select(Resume)
        .join(CandidateProfile, CandidateProfile.id == Resume.candidate_id)
        .where(Resume.id == resume_id, CandidateProfile.user_id == user_id)
    )
    if resume is None:
        raise NotFoundError("Resume not found")
    return resume


def delete_my_resume(session: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> None:
    resume = get_my_resume(session, user_id, resume_id)
    path = Path(resume.file_path)
    session.delete(resume)
    session.commit()
    path.unlink(missing_ok=True)  # after commit: a failed delete never leaves a dangling row


def reprocess_my_resume(session: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    resume = get_my_resume(session, user_id, resume_id)
    if resume.parsing_status not in (ResumeStatus.FAILED,):
        raise ConflictError(
            f"Only failed resumes can be reprocessed (status: {resume.parsing_status})"
        )
    return resume


# ---------------------------------------------------------------- apply to profile


def apply_to_profile(
    session: Session, user_id: uuid.UUID, resume_id: uuid.UUID, body: ResumeApplyRequest
) -> CandidateProfile:
    """Copy the candidate-confirmed data into their profile. Nothing is applied without this call.

    Skills are merged: resume skills are added (source=resume); existing skills are kept.
    """
    resume = get_my_resume(session, user_id, resume_id)
    if resume.parsing_status not in (ResumeStatus.PARSED, ResumeStatus.REVIEWED):
        raise ConflictError("Resume has not been parsed successfully")
    profile = candidates.get_my_profile(session, user_id)

    if body.full_name is not None:
        profile.full_name = body.full_name
    if body.location is not None:
        profile.location = body.location
    if body.experience_years is not None:
        profile.experience_years = body.experience_years
    if body.profile_summary is not None:
        profile.profile_summary = body.profile_summary
    if body.education is not None:
        profile.education = [e.model_dump(mode="json") for e in body.education]
    if body.projects is not None:
        profile.projects = [p.model_dump(mode="json") for p in body.projects]

    resolved = resolve_or_create_skills(session, (s.name for s in body.skills))
    existing = {cs.skill_id: cs for cs in profile.skills}
    for item in body.skills:
        skill = resolved[normalize_skill_name(item.name)]
        if skill.id in existing:
            cs = existing[skill.id]
            cs.proficiency = item.proficiency if item.proficiency is not None else cs.proficiency
            if item.experience_months is not None:
                cs.experience_months = item.experience_months
        else:
            new = CandidateSkill(
                skill_id=skill.id,
                proficiency=item.proficiency,
                experience_months=item.experience_months,
                source=SkillSource.RESUME,
            )
            profile.skills.append(new)
            existing[skill.id] = new

    resume.parsing_status = ResumeStatus.REVIEWED
    resume.reviewed_at = datetime.now(UTC)
    session.commit()
    session.expire_all()
    return candidates.get_my_profile(session, user_id)


def parsed_view(resume: Resume) -> ParsedResume | None:
    return ParsedResume.model_validate(resume.parsed_data) if resume.parsed_data else None
