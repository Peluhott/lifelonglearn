import json
import uuid

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from api import db
from api.main import app
from tutor.graph import build_graph


class FakeSessions:
    """In-memory stand-in for db.PostgresSessions so API tests don't need Postgres."""

    def __init__(self):
        self.rows = {}

    def create(self, session_id, prompt):
        self.rows[session_id] = {"id": str(session_id), "title": prompt[:60], "created_at": str(len(self.rows))}

    def set_title(self, session_id, title):
        self.rows[session_id]["title"] = title

    def delete(self, session_id):
        self.rows.pop(session_id, None)

    def list(self):
        return sorted(self.rows.values(), key=lambda r: r["created_at"], reverse=True)


@pytest.fixture
def client(monkeypatch):
    # TestClient without `with` skips the lifespan, so Postgres is never opened; plug in memory versions instead
    monkeypatch.setattr(app.state, "graph", build_graph(InMemorySaver(serde=db.serializer())), raising=False)
    monkeypatch.setattr(app.state, "sessions", FakeSessions(), raising=False)
    return TestClient(app)


def parse_sse(body):
    """Split an SSE body into (event name, data dict) pairs."""
    events = []
    for frame in body.strip().split("\n\n"):
        event_line, data_line = frame.split("\n")
        events.append((event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: "))))
    return events


def stream(client, prompt="help me with the chain rule"):
    response = client.post("/tutor/stream", json={"prompt": prompt})
    assert response.status_code == 200
    return parse_sse(response.text)


def test_stream_sends_events_in_order(client):
    events = stream(client)

    assert [name for name, _ in events] == ["session", "intake", "plan", "lessons", "review", "done"]


def test_lessons_event_holds_every_step_with_image_urls(client):
    lessons = dict(stream(client))["lessons"]["lessons"]

    assert [(l["index"], l["total"], l["step"]) for l in lessons] == [(0, 2, "step one"), (1, 2, "step two")]
    assert lessons[0]["image_url"] == "/images/fake.png"
    assert lessons[1]["image_url"] is None


def test_llm_failure_becomes_error_event_and_drops_the_session(client, fake_llm):
    fake_llm.error = RuntimeError("gemini down")

    events = stream(client)

    assert [name for name, _ in events] == ["session", "error"]
    assert events[1][1] == {"message": "gemini down"}
    assert client.get("/sessions").json() == []


def test_empty_prompt_is_rejected(client):
    response = client.post("/tutor/stream", json={"prompt": ""})

    assert response.status_code == 422


def test_session_is_listed_with_intake_title(client):
    session_id = dict(stream(client))["session"]["id"]

    assert [(s["id"], s["title"]) for s in client.get("/sessions").json()] == [(session_id, "chain rule")]


def test_saved_session_can_be_reopened(client):
    session_id = dict(stream(client, "explain the chain rule"))["session"]["id"]

    saved = client.get(f"/sessions/{session_id}").json()

    assert saved["prompt"] == "explain the chain rule"
    assert saved["plan"]["steps"] == ["step one", "step two"]
    assert [l["step"] for l in saved["lessons"]] == ["step one", "step two"]
    assert saved["lessons"][0]["image_url"] == "/images/fake.png"
    assert len(saved["review"]["questions"]) == 2


def test_unknown_session_is_404(client):
    assert client.get(f"/sessions/{uuid.uuid4()}").status_code == 404
