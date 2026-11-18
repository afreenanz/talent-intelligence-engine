"""Worker tasks, run in-process against the test transaction (no broker needed)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.enums import ResumeStatus
from app.domains.resumes.models import Resume
from app.domains.resumes.router import get_resume_processor
from app.main import app
from app.worker import tasks
from tests.conftest import auth_header, register_and_login
from tests.pdf_factory import SAMPLE_RESUME_LINES, make_pdf


@pytest.fixture
def worker_session(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Tasks open their own sessions; point them at the test transaction and record enqueues."""

    @contextmanager
    def same_session() -> Iterator[Session]:
        yield db_session

    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: same_session)
    queued: list[str] = []
    monkeypatch.setattr(tasks.process_resume, "delay", queued.append)
    return queued


def _upload(client: TestClient, h: dict[str, str]) -> str:
    app.dependency_overrides[get_resume_processor] = lambda: lambda _rid: None  # broker "down"
    pdf = make_pdf(SAMPLE_RESUME_LINES)
    r = client.post(
        "/api/v1/candidates/resume", files={"file": ("cv.pdf", pdf, "application/pdf")}, headers=h
    )
    return str(r.json()["id"])


def test_requeues_only_resumes_stuck_for_too_long(
    client: TestClient, db_session: Session, worker_session: list[str]
) -> None:
    h = auth_header(register_and_login(client))
    stuck, fresh = _upload(client, h), _upload(client, h)
    long_ago = datetime.now(UTC) - timedelta(minutes=30)
    # A worker died mid-task: 'processing', untouched for 30 minutes.
    db_session.execute(
        update(Resume)
        .where(Resume.id == stuck)
        .values(parsing_status=ResumeStatus.PROCESSING, updated_at=long_ago)
    )
    db_session.flush()

    assert tasks.requeue_stale_resumes() == 1
    assert worker_session == [stuck]  # the fresh upload is left alone
    db_session.expire_all()
    assert db_session.get(Resume, stuck).parsing_status is ResumeStatus.PENDING  # type: ignore[union-attr]
    assert db_session.get(Resume, fresh).parsing_status is ResumeStatus.PENDING  # type: ignore[union-attr]
