"""Agent graph behaviour with a scripted LLM against a real database (no network)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.agent.graph import MAX_MODEL_CALLS, check_grounding
from app.domains.agent.router import llm_dependency
from app.domains.ingestion import service as ingestion
from app.domains.interactions.models import SavedJob
from app.domains.search.deps import embedder_dependency
from app.domains.search.indexing import embed_jobs
from app.integrations.llm.base import LLMUnavailableError
from app.main import app
from tests.conftest import auth_header, register_and_login
from tests.fakes import HashingEmbedder, ScriptedToolLLM, last_tool_result, text_turn, tool_turn

pytestmark = pytest.mark.usefixtures("taxonomy")
CHAT = "/api/v1/agent/chat"


@pytest.fixture(autouse=True)
def corpus(db_session: Session) -> Iterator[None]:
    ingestion.ingest(
        db_session,
        [
            {
                "external_id": f"b{i}",
                "title": "Backend Engineer",
                "company": f"Acme {i}",
                "description": "Build Python services and APIs for payments, owned end to end.",
                "location": "Bengaluru",
                "salary_text": "18-25 LPA",
                "required_skills": ["Python"],
            }
            for i in range(3)
        ],
        source="agent",
        now=datetime.now(UTC),
    )
    emb = HashingEmbedder()
    embed_jobs(db_session, emb)
    app.dependency_overrides[embedder_dependency] = lambda: emb
    yield
    app.dependency_overrides.pop(embedder_dependency, None)
    app.dependency_overrides.pop(llm_dependency, None)


def use(llm: ScriptedToolLLM) -> ScriptedToolLLM:
    app.dependency_overrides[llm_dependency] = lambda: llm
    return llm


def first_job_id(history: list[dict[str, Any]]) -> str:
    return str(last_tool_result(history, "search_jobs")["data"]["results"][0]["job_id"])


SEARCH = tool_turn(
    ("search_jobs", {"query": "python backend", "city": "Bengaluru", "min_salary": 1500000})
)
CITE_FIRST = text_turn(lambda h: f"Top match: Backend Engineer [job_id: {first_job_id(h)}]")


def test_search_answer_is_grounded_and_persisted(client: TestClient) -> None:
    llm = use(ScriptedToolLLM(SEARCH, CITE_FIRST))
    h = auth_header(register_and_login(client))
    body = client.post(
        CHAT, json={"message": "backend jobs in Bangalore above 15 LPA"}, headers=h
    ).json()
    assert body["status"] == "completed" and body["grounded"] is True
    assert body["tool_calls"][0]["tool"] == "search_jobs" and body["tool_calls"][0]["ok"]
    results = last_tool_result(llm.calls[1], "search_jobs")["data"]["results"]
    assert results and all(r["salary_max"] >= 1_500_000 for r in results)  # filter really applied
    detail = client.get(f"/api/v1/agent/conversations/{body['conversation_id']}", headers=h).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["tool_metadata"]["grounded"] is True


def test_hallucinated_job_id_triggers_one_correction(client: TestClient) -> None:
    fake = "11111111-2222-3333-4444-555555555555"
    llm = use(ScriptedToolLLM(SEARCH, text_turn(f"Try job {fake}"), CITE_FIRST))
    h = auth_header(register_and_login(client))
    body = client.post(CHAT, json={"message": "find jobs"}, headers=h).json()
    assert body["grounded"] is True and fake not in body["reply"]
    correction = llm.calls[2][-1]
    assert correction["role"] == "user" and "Automatic check" in correction["text"]


def test_persistent_hallucination_is_flagged_not_hidden(client: TestClient) -> None:
    fake = "11111111-2222-3333-4444-555555555555"
    use(ScriptedToolLLM(SEARCH, text_turn(f"Job {fake}"), text_turn(f"Job {fake}")))
    h = auth_header(register_and_login(client))
    body = client.post(CHAT, json={"message": "find jobs"}, headers=h).json()
    assert body["grounded"] is False and "not returned by any tool" in body["grounding_issues"][0]


def test_save_requires_confirmation_then_runs(client: TestClient, db_session: Session) -> None:
    use(
        ScriptedToolLLM(
            SEARCH,
            CITE_FIRST,
            tool_turn(("save_job", lambda h: {"job_id": first_job_id(h)})),
            text_turn("I've saved it to your saved jobs."),
        )
    )
    h = auth_header(register_and_login(client))
    conv = client.post(CHAT, json={"message": "find jobs"}, headers=h).json()["conversation_id"]
    paused = client.post(
        CHAT, json={"message": "save the first", "conversation_id": conv}, headers=h
    ).json()
    assert (
        paused["status"] == "awaiting_confirmation"
        and paused["pending_actions"][0]["tool"] == "save_job"
    )
    assert db_session.scalar(select(func.count()).select_from(SavedJob)) == 0  # nothing yet

    blocked = client.post(CHAT, json={"message": "hello?", "conversation_id": conv}, headers=h)
    assert blocked.status_code == 409

    done = client.post(
        f"/api/v1/agent/conversations/{conv}/confirm", json={"approved": True}, headers=h
    ).json()
    assert done["status"] == "completed" and done["grounded"] is True
    assert done["tool_calls"][-1] == {
        "tool": "save_job",
        "arguments": done["tool_calls"][-1]["arguments"],
        "ok": True,
        "error_code": None,
        "confirmed": True,
    }
    assert db_session.scalar(select(func.count()).select_from(SavedJob)) == 1


def test_declined_action_is_not_performed_and_claim_is_caught(
    client: TestClient, db_session: Session
) -> None:
    use(
        ScriptedToolLLM(
            SEARCH,
            CITE_FIRST,
            tool_turn(("save_job", lambda h: {"job_id": first_job_id(h)})),
            text_turn("I've saved it."),  # lies after a decline
            text_turn("Okay, I did not save it."),
        )
    )
    h = auth_header(register_and_login(client))
    conv = client.post(CHAT, json={"message": "find"}, headers=h).json()["conversation_id"]
    client.post(CHAT, json={"message": "save it", "conversation_id": conv}, headers=h)
    done = client.post(
        f"/api/v1/agent/conversations/{conv}/confirm", json={"approved": False}, headers=h
    ).json()
    assert db_session.scalar(select(func.count()).select_from(SavedJob)) == 0
    assert done["tool_calls"][-1]["error_code"] == "declined_by_user"
    assert done["reply"] == "Okay, I did not save it." and done["grounded"] is True


def test_preference_update_is_confirmed_and_stored(client: TestClient) -> None:
    use(
        ScriptedToolLLM(
            tool_turn(
                (
                    "update_candidate_preferences",
                    {
                        "key": "role_categories",
                        "value": {"prefer": ["backend"], "avoid": ["frontend"]},
                    },
                )
            ),
            text_turn("Your preference has been updated."),
        )
    )
    h = auth_header(register_and_login(client))
    conv = client.post(CHAT, json={"message": "remember I prefer backend"}, headers=h).json()[
        "conversation_id"
    ]
    client.post(f"/api/v1/agent/conversations/{conv}/confirm", json={"approved": True}, headers=h)
    stored = client.get("/api/v1/candidates/me/preferences", headers=h).json()
    assert (
        stored[0]["value"] == {"prefer": ["backend"], "avoid": ["frontend"]}
        and stored[0]["source"] == "agent"
    )


def test_invalid_and_unknown_tool_calls_return_structured_errors(client: TestClient) -> None:
    llm = use(
        ScriptedToolLLM(
            tool_turn(
                ("search_jobs", {"top_k": 999}),
                ("delete_everything", {}),
                ("get_saved_jobs", {"candidate_id": "someone-else"}),
            ),
            text_turn("Sorry, I couldn't do that."),
        )
    )
    h = auth_header(register_and_login(client))
    body = client.post(CHAT, json={"message": "x"}, headers=h).json()
    codes = [t["error_code"] for t in body["tool_calls"]]
    assert codes == [
        "invalid_arguments",
        "unknown_tool",
        "invalid_arguments",
    ]  # candidate_id is not an argument
    sent_back = [h["result"]["error_code"] for h in llm.calls[1] if h.get("role") == "tool"]
    assert sent_back == codes  # every call got exactly one result before the next model call


def test_step_limit_stops_runaway_tool_loops(client: TestClient) -> None:
    llm = use(
        ScriptedToolLLM(*[tool_turn(("get_saved_jobs", {})) for _ in range(MAX_MODEL_CALLS + 2)])
    )
    h = auth_header(register_and_login(client))
    body = client.post(CHAT, json={"message": "loop"}, headers=h).json()
    assert body["status"] == "completed" and body["grounding_issues"] == ["step_limit"]
    assert len(llm.calls) == MAX_MODEL_CALLS


def test_llm_outage_is_503(client: TestClient) -> None:
    use(ScriptedToolLLM(LLMUnavailableError("down")))
    h = auth_header(register_and_login(client))
    r = client.post(CHAT, json={"message": "hi"}, headers=h)
    assert r.status_code == 503 and r.json()["error"]["code"] == "upstream_unavailable"


def test_conversation_history_carries_across_turns_and_context_is_fresh(client: TestClient) -> None:
    llm = use(ScriptedToolLLM(text_turn("Hello."), text_turn("Still here.")))
    h = auth_header(register_and_login(client))
    client.put(
        "/api/v1/candidates/me/preferences/location_type",
        json={"value": {"value": "remote"}},
        headers=h,
    )
    conv = client.post(CHAT, json={"message": "first"}, headers=h).json()["conversation_id"]
    client.post(CHAT, json={"message": "second", "conversation_id": conv}, headers=h)
    texts = [m.get("text") for m in llm.calls[1] if m["role"] in ("user", "assistant")]
    assert texts == ["first", "Hello.", "second"]
    assert "location_type (stated)" in llm.system  # preferences come from the DB, not chat history


def test_conversations_are_private_and_deletable(client: TestClient) -> None:
    use(ScriptedToolLLM(text_turn("Hi.")))
    alice = auth_header(register_and_login(client, "alice@example.com"))
    bob = auth_header(register_and_login(client, "bob@example.com"))
    conv = client.post(CHAT, json={"message": "hi"}, headers=alice).json()["conversation_id"]
    assert client.get(f"/api/v1/agent/conversations/{conv}", headers=bob).status_code == 404
    assert (
        client.post(CHAT, json={"message": "x", "conversation_id": conv}, headers=bob).status_code
        == 404
    )
    assert client.get("/api/v1/agent/conversations", headers=bob).json() == []
    assert client.delete(f"/api/v1/agent/conversations/{conv}", headers=alice).status_code == 204
    assert client.get(f"/api/v1/agent/conversations/{conv}", headers=alice).status_code == 404


@pytest.mark.parametrize(
    ("text", "seen", "actions", "n_issues"),
    [
        (
            "Job [job_id: 3f2a9c1e-8b7d-4e21-9a6f-1c2d3e4f5a6b]",
            {"3f2a9c1e-8b7d-4e21-9a6f-1c2d3e4f5a6b"},
            set(),
            0,
        ),
        (
            "Job 3F2A9C1E-8B7D-4E21-9A6F-1C2D3E4F5A6B",
            {"3f2a9c1e-8b7d-4e21-9a6f-1c2d3e4f5a6b"},
            set(),
            0,
        ),
        ("I've saved it.", set(), set(), 1),
        ("I've saved it.", set(), {"save_job"}, 0),
        ("I'll remember that you prefer backend.", set(), set(), 1),
        ("Here are three jobs you might like.", set(), set(), 0),
    ],
)
def test_check_grounding_rules(text: str, seen: set[str], actions: set[str], n_issues: int) -> None:
    assert len(check_grounding(text, seen, actions)) == n_issues
