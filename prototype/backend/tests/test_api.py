"""Meaningful smoke coverage for the local demo's data and approval boundary."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(tmp_path / "strivetrack-test.sqlite3")
    with TestClient(app) as session:
        response = session.post("/api/auth/login", json={"email": "teacher@strivetrack.demo", "password": "strivetrack-demo"})
        assert response.status_code == 200
        session.headers["Authorization"] = "Bearer " + response.json()["token"]
        yield session


def new_goal(client):
    result = client.post("/api/goals", json={
        "title": "Plan a classroom supply pickup",
        "skill_description": "Choose the order of three supply pickup tasks and explain the plan.",
        "success_criteria": "Explain the first step using the approved picture cards.",
        "accommodations": ["Visual step cards", "Extra processing time"],
    })
    assert result.status_code == 201, result.text
    return result.json()


def new_activity(client, goal):
    result = client.post("/api/activities", json={
        "goal_id": goal["id"], "title": "Supply pickup practice",
        "content": "Follow these steps in order:\n1. Pick up the tray.\n2. Collect three supplies.\n3. Return to the classroom.\n\nVisual step cards\nExtra processing time",
    })
    assert result.status_code == 201, result.text
    return result.json()


def test_demo_login_and_authentication(client):
    assert len(client.get("/api/demo-users").json()) == 3
    assert "password" not in str(client.get("/api/demo-users").json())
    assert client.get("/api/auth/me").json()["name"] == "Maya Brooks"
    assert client.post("/api/auth/login", json={"email": "teacher@strivetrack.demo", "password": "wrong"}).status_code == 401
    assert client.get("/api/goals", headers={"Authorization": "Bearer invalid"}).status_code == 401
    client.headers.pop("Authorization")
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/health").json()["status"] == "ok"


def test_seed_counts_filters_sort_and_pagination(client):
    for entity, minimum in (("goals", 30), ("activities", 30), ("revisions", 30), ("observations", 28)):
        result = client.get("/api/" + entity, params={"page_size": 7}).json()
        assert result["total"] >= minimum
        assert len(result["items"]) == 7
        assert result["pages"] >= 4
    response = client.get("/api/goals", params={"status": "active", "category": "Workplace", "sort": "title", "order": "asc", "page_size": 100}).json()
    assert all(g["status"] == "active" and g["category"] == "Workplace" for g in response["items"])
    titles = [g["title"].casefold() for g in response["items"]]
    assert titles == sorted(titles)
    assert client.get("/api/goals", params={"q": "café"}).json()["total"] == 1
    assert client.get("/api/goals", params={"q": "a completely absent activity"}).json()["items"] == []
    assert client.get("/api/goals", params={"page": 0}).status_code == 422
    assert client.get("/api/goals", params={"sort": "not_a_column"}).status_code == 422


def test_goal_activity_observation_crud_and_relationships(client):
    goal = new_goal(client)
    activity = new_activity(client, goal)
    assert client.get("/api/activities/" + activity["id"]).json()["goal_id"] == goal["id"]
    assert client.delete("/api/goals/" + goal["id"]).status_code == 409
    changed = client.patch("/api/goals/" + goal["id"], json={"title": "Supply pickup planning goal"})
    assert changed.status_code == 200
    assert changed.json()["title"] == "Supply pickup planning goal"
    observation = client.post("/api/observations", json={"activity_id": activity["id"], "note": "The learner selected a first card and explained the choice.", "context": "Quiet practice room"}).json()
    changed = client.patch("/api/observations/" + observation["id"], json={"note": "The learner revised the plan after noticing the tray was unavailable."})
    assert changed.status_code == 200
    assert client.get("/api/observations", params={"activity_id": activity["id"]}).json()["total"] == 1
    assert client.delete("/api/observations/" + observation["id"]).status_code == 200
    assert client.get("/api/observations/" + observation["id"]).status_code == 404
    assert client.patch("/api/activities/" + activity["id"], json={"title": "Collect classroom supplies"}).status_code == 200
    assert client.delete("/api/activities/" + activity["id"]).status_code == 200
    assert client.delete("/api/goals/" + goal["id"]).status_code == 200
    assert client.get("/api/goals/" + goal["id"]).status_code == 404


def test_validation_and_unknown_relationships(client):
    assert client.post("/api/goals", json={"title": " "}).status_code == 422
    assert client.post("/api/activities", json={"goal_id": "missing", "title": "Missing goal activity", "content": "Choose a sensible plan for the work task."}).status_code == 404
    goal = new_goal(client)
    assert client.patch("/api/goals/" + goal["id"], json={"accommodations": ["Visual step cards", "Visual step cards"]}).status_code == 422
    assert client.patch("/api/goals/" + goal["id"], json={"due_date": "not-a-date"}).status_code == 422
    assert client.patch("/api/goals/" + goal["id"], json={"unrecognized": True}).status_code == 422
    assert client.get("/api/activities/not-found").json()["detail"]


def test_checker_quotes_verbatim_evidence_and_unsure(client):
    activity = client.get("/api/activities/a01").json()
    result = client.post("/api/checks", json={"activity_id": "a01"})
    assert result.status_code == 201
    check = result.json()
    assert check["result"] == "mismatch"
    assert check["findings"]
    assert all(finding["evidence"] in activity["content"] for finding in check["findings"])
    assert client.post("/api/checks", json={"activity_id": "a02"}).json()["result"] == "aligned"
    assert client.post("/api/checks", json={"activity_id": "a06"}).json()["result"] == "unsure"
    assert client.post("/api/checks", json={"activity_id": "a30"}).status_code == 409


def test_revision_guard_approval_history_and_learner_gate(client):
    goal = new_goal(client)
    activity = new_activity(client, goal)
    identifier = activity["id"]
    assert client.get("/api/try/" + identifier).status_code == 409
    assert client.patch("/api/activities/" + identifier, json={"status": "approved"}).status_code == 409
    revision = client.post("/api/revisions", json={"activity_id": identifier}).json()
    assert revision["status"] == "draft"
    assert all(support in revision["content"] for support in goal["accommodations"])
    revision_path = "/api/revisions/" + revision["id"]
    missing_content = revision["content"].replace("Visual step cards", "")
    blocked = client.patch(revision_path, json={"content": missing_content})
    assert blocked.json()["status"] == "blocked"
    assert "Visual step cards" in blocked.json()["blocked_reason"]
    assert client.post(revision_path + "/approve", json={}).status_code == 409
    assert client.patch(revision_path, json={"content": revision["content"]}).json()["status"] == "draft"
    assert client.post(revision_path + "/approve", json={}).json()["status"] == "approved"
    learner = client.get("/api/try/" + identifier)
    assert learner.status_code == 200
    assert len(learner.json()["steps"]) == 3
    assert client.patch(revision_path, json={"content": "A replacement with no supports."}).status_code == 409
    assert client.delete(revision_path).status_code == 409
    assert client.delete("/api/activities/" + identifier).status_code == 409
    history = client.get("/api/audit", params={"q": "approved", "page_size": 100}).json()["items"]
    assert any(item["target_id"] == identifier and item["version"] == revision["version"] for item in history)
    plan = list(reversed(learner.json()["steps"]))
    result = client.post("/api/try/" + identifier + "/submit", json={"ordered_steps": plan})
    assert result.status_code == 201
    assert result.json()["ordered_steps"] == plan
    assert client.post("/api/try/" + identifier + "/submit", json={"ordered_steps": ["Invented card", "Another invented card"]}).status_code == 422


def test_support_change_revokes_access_and_new_revision_restores_it(client):
    before = client.get("/api/try/a02")
    assert before.status_code == 200
    goal = before.json()["goal"]
    assert client.patch("/api/goals/" + goal["id"], json={"accommodations": goal["accommodations"] + ["A short planning pause"]}).status_code == 200
    assert client.get("/api/try/a02").status_code == 409
    revision = client.post("/api/revisions", json={"activity_id": "a02"}).json()
    assert "A short planning pause" in revision["content"]
    assert all(step in revision["content"] for step in before.json()["steps"])
    assert client.post("/api/revisions/" + revision["id"] + "/approve").status_code == 200
    assert client.get("/api/try/a02").status_code == 200


def test_saving_unchanged_supports_keeps_existing_teacher_approval(client):
    before = client.get("/api/try/a02")
    assert before.status_code == 200
    goal = before.json()["goal"]
    changed = client.patch("/api/goals/" + goal["id"], json={
        "title": goal["title"] + " · reference copy",
        "accommodations": goal["accommodations"],
    })
    assert changed.status_code == 200
    assert client.get("/api/activities/a02").json()["status"] == "approved"
    assert client.get("/api/try/a02").status_code == 200
    # The order of the support list does not change the approved support set.
    assert client.patch("/api/goals/" + goal["id"], json={"accommodations": list(reversed(goal["accommodations"]))}).status_code == 200
    assert client.get("/api/try/a02").status_code == 200


def test_reject_and_delete_draft_flows(client):
    revision = client.post("/api/revisions", json={"activity_id": "a01"}).json()
    path = "/api/revisions/" + revision["id"]
    assert client.post(path + "/reject", json={"reason": ""}).status_code == 422
    assert client.post(path + "/reject", json={"reason": "The task cards need a clearer workplace context."}).json()["status"] == "rejected"
    assert client.post(path + "/approve").status_code == 409
    another = client.post("/api/revisions", json={"activity_id": "a01"}).json()
    assert client.delete("/api/revisions/" + another["id"]).status_code == 200
    assert client.get("/api/revisions/" + another["id"]).status_code == 404


def test_dashboard_and_reset(client):
    stats = client.get("/api/dashboard").json()
    assert stats["stats"]["active_goals"] == 27
    assert stats["stats"]["approved"] == 10
    assert len(stats["weekly"]) == 7
    assert sum(day["checked"] for day in stats["weekly"]) == 30
    new_goal(client)
    assert client.get("/api/goals").json()["total"] == 31
    result = client.post("/api/reset")
    assert result.status_code == 200
    assert result.json()["counts"]["goals"] == 30
    assert client.get("/api/goals").json()["total"] == 30
    assert client.get("/api/auth/me").status_code == 200


def test_sqlite_persistence(tmp_path):
    path = tmp_path / "persistent.sqlite3"
    with TestClient(create_app(path)) as first:
        first.headers["Authorization"] = "Bearer demo-u1"
        new_goal(first)
    with TestClient(create_app(path)) as second:
        second.headers["Authorization"] = "Bearer demo-u1"
        assert second.get("/api/goals").json()["total"] == 31
