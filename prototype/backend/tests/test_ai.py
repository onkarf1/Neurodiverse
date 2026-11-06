"""AI assistance stays inside the code-enforced boundaries."""
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import AIAssistant, locate_quote
from app.main import create_app


def fake_model(reply: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"choices": [{"message": {"content": "<think>hidden</think>```json\n" + json.dumps(reply) + "\n```"}}]})
    return AIAssistant(api_key="test-key", model="test-model", transport=httpx.MockTransport(handler))


def signed_in(app):
    session = TestClient(app)
    session.__enter__()
    session.headers["Authorization"] = "Bearer " + session.post("/api/auth/login", json={"email": "teacher@strivetrack.demo", "password": "strivetrack-demo"}).json()["token"]
    return session


def test_locate_quote_ignores_case_and_spacing():
    assert locate_quote("Follow these   steps\nin order:", "follow these steps in order") == "Follow these   steps\nin order"
    assert locate_quote("Wipe the counter", "Invented sentence here") is None


def test_ai_check_keeps_only_verified_quotes(tmp_path: Path):
    ai = fake_model({"result": "mismatch", "summary": "The worksheet sequences the task.", "findings": [
        {"type": "Skill bypass", "explanation": "Steps are pre-ordered.", "evidence": "follow these steps in order:"},
        {"type": "Answer given", "explanation": "Made up.", "evidence": "This sentence is not in the activity"},
        {"type": "Support not stated", "explanation": "Duplicate of the rules.", "evidence": "Check each step after you finish."},
    ], "demand_map": [
        {"skill": "Planning", "goal_targets": True, "activity": "done_for_learner", "note": "Steps are numbered."},
        {"skill": "working-memory", "goal_targets": False, "activity": "not_required"},
        {"skill": "telepathy", "goal_targets": True, "activity": "learner_does"},
        {"skill": "sequencing", "goal_targets": "yes", "activity": "sometimes"},
    ]})
    client = signed_in(create_app(tmp_path / "ai.sqlite3", ai=ai))
    content = client.get("/api/activities/a01").json()["content"]
    check = client.post("/api/checks", json={"activity_id": "a01"}).json()
    assert check["mode"] == "ai-assisted" and check["ai_model"] == "test-model"
    assert all(finding["evidence"] in content for finding in check["findings"])
    assert any(finding["source"] == "ai" for finding in check["findings"])
    assert not any(f["source"] == "ai" and "support" in f["type"].casefold() for f in check["findings"])
    assert "1 AI suggestion was removed" in check["ai_note"]
    assert [(row["skill"], row["goal_targets"], row["activity"]) for row in check["demand_map"]] == [("planning", True, "done_for_learner"), ("working_memory", False, "not_required")]


def test_rules_build_a_demand_map_without_ai(client):
    rows = {row["skill"]: row for row in client.post("/api/checks", json={"activity_id": "a01"}).json()["demand_map"]}
    assert rows["planning"]["goal_targets"] and rows["planning"]["activity"] == "done_for_learner"
    assert client.post("/api/checks", json={"activity_id": "a02"}).json()["demand_map"][0]["activity"] == "learner_does"


def test_ai_revision_cannot_drop_supports(tmp_path: Path):
    ai = fake_model({"title": "Plan  your café opening", "instructions": "You choose the order. Tell your teacher why.", "task_cards": ["🧽 Get the cloth", "🧼 Wipe the counter", "☕ Set out cups"], "reflection": "What helped?", "rationale": "Removed the numbering."})
    client = signed_in(create_app(tmp_path / "ai.sqlite3", ai=ai))
    goal = client.get("/api/goals/" + client.get("/api/activities/a01").json()["goal_id"]).json()
    revision = client.post("/api/revisions", json={"activity_id": "a01"}).json()
    assert revision["mode"] == "ai-assisted" and revision["ai_rationale"] == "Removed the numbering."
    assert revision["status"] == "draft"
    assert all(support in revision["content"] for support in goal["accommodations"])
    cards = revision["content"].split("Step cards:\n")[1].split("\n\n")[0].splitlines()
    assert cards[0] == "• 🧼 Wipe the counter"
    assert revision["content"].startswith("Plan your café opening\n\n")


def test_unreachable_model_falls_back_to_local_rules(tmp_path: Path):
    ai = AIAssistant(api_key="test-key", transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    client = signed_in(create_app(tmp_path / "ai.sqlite3", ai=ai))
    check = client.post("/api/checks", json={"activity_id": "a01"}).json()
    assert check["mode"] == "deterministic-demo" and check["result"] == "mismatch"
    assert "did not respond" in check["ai_note"]
    revision = client.post("/api/revisions", json={"activity_id": "a01"}).json()
    assert revision["mode"] == "deterministic-demo" and "did not respond" in revision["ai_note"]


@pytest.fixture
def client(tmp_path: Path):
    session = signed_in(create_app(tmp_path / "plain.sqlite3"))
    yield session
    session.__exit__(None, None, None)


def test_support_matching_ignores_case_and_spacing(client):
    revision = client.post("/api/revisions", json={"activity_id": "a01"}).json()
    content = revision["content"].replace("Extra processing time", "extra  processing TIME")
    saved = client.patch("/api/revisions/" + revision["id"], json={"content": content})
    assert saved.json()["status"] == "draft"
    assert client.post("/api/revisions/" + revision["id"] + "/approve").status_code == 200
    assert client.get("/api/try/a01").status_code == 200


def test_session_record_keeps_reasoning_and_supports(client):
    data = client.get("/api/try/a02").json()
    supports = data["goal"]["accommodations"]
    result = client.post("/api/try/a02/submit", json={"ordered_steps": list(reversed(data["steps"])), "learner_label": "Learner A", "reasoning": "Gets supplies first so there are fewer trips.", "prompting": "one_prompt", "supports_used": [supports[0].upper()]})
    assert result.status_code == 201, result.text
    session = result.json()["session"]
    assert session["supports_used"] == [supports[0]] and session["prompting"] == "one_prompt"
    listed = client.get("/api/sessions", params={"activity_id": "a02"}).json()
    assert listed["total"] == 1 and listed["items"][0]["reasoning"].startswith("Gets supplies")
    assert client.post("/api/try/a02/submit", json={"ordered_steps": data["steps"], "supports_used": ["A support that was never approved"]}).status_code == 422
    history = client.get("/api/audit", params={"q": "session for Learner A"}).json()["items"]
    assert [item["action"] for item in history] == ["session recorded"]


def test_checks_go_stale_when_goal_or_activity_changes(client):
    activity = client.get("/api/activities/a01").json()
    created = client.post("/api/checks", json={"activity_id": "a01"}).json()
    assert created["stale"] is False
    seeded = client.get("/api/checks", params={"activity_id": "a02"}).json()["items"]
    assert seeded and not any(item["stale"] for item in seeded)
    client.patch("/api/activities/a01", json={"content": activity["content"] + "\nBring a cloth."})
    assert client.get("/api/checks/" + created["id"]).json()["stale_reasons"] == ["activity"]
    goal = client.get("/api/goals/" + activity["goal_id"]).json()
    client.patch("/api/goals/" + goal["id"], json={"success_criteria": goal["success_criteria"] + " Explain one reason."})
    assert client.get("/api/checks/" + created["id"]).json()["stale_reasons"] == ["goal", "activity"]
    assert client.post("/api/checks", json={"activity_id": "a01"}).json()["stale"] is False


def test_approval_retires_older_drafts_and_history_records_edits(client):
    older = client.post("/api/revisions", json={"activity_id": "a01"}).json()
    newer = client.post("/api/revisions", json={"activity_id": "a01"}).json()
    client.patch("/api/revisions/" + older["id"], json={"content": older["content"].replace("Extra processing time", "")})
    assert client.post("/api/revisions/" + newer["id"] + "/approve").status_code == 200
    retired = client.get("/api/revisions/" + older["id"]).json()
    assert retired["status"] == "superseded" and retired["superseded_by"] == newer["version"]
    assert client.post("/api/revisions/" + older["id"] + "/approve").status_code == 409
    observation = client.post("/api/observations", json={"activity_id": "a01", "note": "Chose supplies first."}).json()
    client.patch("/api/observations/" + observation["id"], json={"note": "Chose supplies first, then cups."})
    client.delete("/api/observations/" + observation["id"])
    actions = [item["action"] for item in client.get("/api/audit", params={"page_size": 100, "sort": "created_at"}).json()["items"]]
    assert {"edited draft", "edited observation", "deleted observation"} <= set(actions)
    edited = client.get("/api/audit", params={"q": "Saved teacher edits"}).json()["items"][0]
    assert "Restore the approved accommodation" in edited["detail"]


def test_dashboard_support_share_counts_current_supports(client):
    assert client.get("/api/dashboard").json()["stats"]["accommodations_kept"] == 100
    goal_id = client.get("/api/activities/a02").json()["goal_id"]
    goal = client.get("/api/goals/" + goal_id).json()
    client.patch("/api/goals/" + goal_id, json={"accommodations": goal["accommodations"] + ["Noise-reducing headphones"]})
    assert client.get("/api/dashboard").json()["stats"]["accommodations_kept"] < 100
