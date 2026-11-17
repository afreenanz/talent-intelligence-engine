"""Resume API flows with a scripted LLM, run synchronously against the test transaction."""

import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.resumes import service
from app.domains.resumes.router import get_resume_processor
from app.domains.resumes.schemas import ResumeExtraction
from app.integrations.llm.base import LLMUnavailableError
from app.main import app
from tests.conftest import auth_header, register_and_login
from tests.fakes import ScriptedLLM
from tests.pdf_factory import SAMPLE_RESUME_LINES, make_pdf

UPLOAD = "/api/v1/candidates/resume"
PDF = make_pdf(SAMPLE_RESUME_LINES)

GOOD = ResumeExtraction.model_validate(
    {
        "full_name": "Asha Verma",
        "location": "Bengaluru, India",
        "summary": "Backend engineer who enjoys building reliable APIs.",
        "skills": ["Python", "FastAPI", "Postgres", "Docker", "Kafka", "Kubernetes"],
        "work_experience": [
            {
                "company": "Kestrel Labs",
                "title": "Software Engineer",
                "start_date": "2021-06",
                "end_date": "2023-05",
                "is_current": False,
            },
            {
                "company": "Bluefin Systems",
                "title": "Senior Software Engineer",
                "start_date": "2023-06",
                "end_date": None,
                "is_current": True,
            },
        ],
        "education": [
            {
                "institution": "IIT Madras",
                "degree": "B.Tech",
                "field_of_study": "Computer Science",
                "start_year": 2017,
                "end_year": 2021,
            }
        ],
        "projects": [
            {
                "name": "Job search engine",
                "description": "hybrid retrieval",
                "technologies": ["PostgreSQL"],
            }
        ],
        "preferred_roles": [],
    }
)


pytestmark = pytest.mark.usefixtures("taxonomy")


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM()


@pytest.fixture(autouse=True)
def processor(db_session: Session, llm: ScriptedLLM) -> Iterator[None]:
    app.dependency_overrides[get_resume_processor] = lambda: (
        lambda rid: service.process_resume(db_session, rid, llm, today=date(2026, 11, 17))
    )
    yield
    app.dependency_overrides.pop(get_resume_processor, None)


def upload(client: TestClient, h: dict[str, str], data: bytes = PDF, name: str = "cv.pdf") -> dict:  # type: ignore[type-arg]
    r = client.post(UPLOAD, files={"file": (name, data, "application/pdf")}, headers=h)
    assert r.status_code == 202, r.text
    return client.get(f"/api/v1/candidates/resumes/{r.json()['id']}", headers=h).json()  # type: ignore[no-any-return]


def test_upload_parses_and_removes_ungrounded_skill(client: TestClient, llm: ScriptedLLM) -> None:
    llm.script.append(GOOD)
    h = auth_header(register_and_login(client))
    resume = upload(client, h)
    assert resume["parsing_status"] == "parsed", resume["parsing_error"]
    parsed = resume["parsed_data"]
    names = {s["name"] for s in parsed["skills"]}
    assert "Kubernetes" not in names  # LLM said it; the text doesn't -> removed
    assert "PostgreSQL" in names  # "Postgres" in text resolved through the alias
    assert parsed["experience_years"] == 5.5
    assert any("Kubernetes" in w for w in parsed["warnings"])
    assert resume["llm_model"] == "scripted-fake"
    assert "Kestrel Labs" in llm.prompts[0]  # the extracted text was what we sent


def test_nothing_reaches_the_profile_until_applied(client: TestClient, llm: ScriptedLLM) -> None:
    llm.script.append(GOOD)
    h = auth_header(register_and_login(client))
    client.put("/api/v1/candidates/me", json={"skills": [{"name": "Go"}]}, headers=h)
    resume = upload(client, h)
    assert client.get("/api/v1/candidates/me", headers=h).json()["full_name"] is None

    r = client.post(
        f"/api/v1/candidates/resumes/{resume['id']}/apply",
        json={
            "full_name": "Asha Verma",
            "experience_years": 5.5,
            "skills": [{"name": "Python"}, {"name": "Kafka"}],
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    profile = r.json()
    assert profile["full_name"] == "Asha Verma" and profile["experience_years"] == 5.5
    sources = {s["name"]: s["source"] for s in profile["skills"]}
    assert sources == {
        "Go": "manual",
        "Python": "resume",
        "Kafka": "resume",
    }  # merged, not replaced
    status = client.get(f"/api/v1/candidates/resumes/{resume['id']}", headers=h).json()
    assert status["parsing_status"] == "reviewed"


def test_llm_outage_fails_cleanly_and_reprocess_recovers(
    client: TestClient, llm: ScriptedLLM
) -> None:
    llm.script += [LLMUnavailableError("down"), GOOD]
    h = auth_header(register_and_login(client))
    resume = upload(client, h)
    assert resume["parsing_status"] == "failed"
    assert "temporarily unavailable" in resume["parsing_error"]
    assert resume["parsed_data"] is None  # nothing half-baked stored

    r = client.post(f"/api/v1/candidates/resumes/{resume['id']}/reprocess", headers=h)
    assert r.status_code == 202
    again = client.get(f"/api/v1/candidates/resumes/{resume['id']}", headers=h).json()
    assert again["parsing_status"] == "parsed"


def test_image_only_pdf_fails_without_calling_llm(client: TestClient, llm: ScriptedLLM) -> None:
    h = auth_header(register_and_login(client))
    resume = upload(client, h, data=make_pdf([]))
    assert resume["parsing_status"] == "failed" and "OCR" in resume["parsing_error"]
    assert llm.prompts == []


def test_apply_before_parse_is_conflict(client: TestClient, llm: ScriptedLLM) -> None:
    llm.script.append(LLMUnavailableError("down"))
    h = auth_header(register_and_login(client))
    resume = upload(client, h)
    r = client.post(f"/api/v1/candidates/resumes/{resume['id']}/apply", json={}, headers=h)
    assert r.status_code == 409


@pytest.mark.parametrize(
    ("data", "code"),
    [(b"PK\x03\x04 a docx file", 415), (b"", 415), (b"%PDF-" + b"0" * (5 * 1024 * 1024), 413)],
)
def test_upload_validation(client: TestClient, data: bytes, code: int) -> None:
    h = auth_header(register_and_login(client))
    r = client.post(UPLOAD, files={"file": ("x.pdf", data, "application/pdf")}, headers=h)
    assert r.status_code == code


def test_filename_is_sanitised_and_not_used_as_path(client: TestClient, llm: ScriptedLLM) -> None:
    llm.script.append(GOOD)
    h = auth_header(register_and_login(client))
    resume = upload(client, h, name="../../etc/passwd<script>.pdf")
    assert resume["original_filename"] == "passwd_script_.pdf"


def test_resumes_are_private_to_their_owner(client: TestClient, llm: ScriptedLLM) -> None:
    llm.script.append(GOOD)
    alice = auth_header(register_and_login(client, "alice@example.com"))
    bob = auth_header(register_and_login(client, "bob@example.com"))
    rid = upload(client, alice)["id"]

    base = f"/api/v1/candidates/resumes/{rid}"
    assert client.get(base, headers=bob).status_code == 404
    assert client.post(f"{base}/apply", json={}, headers=bob).status_code == 404
    assert client.delete(base, headers=bob).status_code == 404
    assert client.get("/api/v1/candidates/resumes", headers=bob).json() == []
    assert client.get(base, headers=alice).status_code == 200


def test_delete_removes_row_and_file(
    client: TestClient, llm: ScriptedLLM, db_session: Session
) -> None:
    llm.script.append(GOOD)
    h = auth_header(register_and_login(client))
    rid = upload(client, h)["id"]
    from pathlib import Path

    from app.domains.resumes.models import Resume

    path = Path(db_session.get(Resume, uuid.UUID(rid)).file_path)  # type: ignore[union-attr]
    assert path.exists()
    assert client.delete(f"/api/v1/candidates/resumes/{rid}", headers=h).status_code == 204
    assert not path.exists()
    assert client.get(f"/api/v1/candidates/resumes/{rid}", headers=h).status_code == 404


def test_upload_without_llm_configured_is_503_and_stores_nothing(client: TestClient) -> None:
    app.dependency_overrides.pop(
        get_resume_processor, None
    )  # use the real factory: no key in tests
    from app.integrations.llm.factory import get_llm_provider

    get_llm_provider.cache_clear()
    h = auth_header(register_and_login(client))
    r = client.post(UPLOAD, files={"file": ("cv.pdf", PDF, "application/pdf")}, headers=h)
    assert r.status_code == 503 and r.json()["error"]["code"] == "upstream_unavailable"
    assert client.get("/api/v1/candidates/resumes", headers=h).json() == []
