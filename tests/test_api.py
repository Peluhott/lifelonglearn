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
        self.asked = {}  # session id -> follow-ups

    def create(self, session_id, prompt):
        self.rows[session_id] = {"id": str(session_id), "title": prompt[:60], "created_at": str(len(self.rows))}

    def set_title(self, session_id, title):
        self.rows[session_id]["title"] = title

    def delete(self, session_id):
        self.asked.pop(session_id, None)
        return self.rows.pop(session_id, None) is not None

    def add_followup(self, session_id, followup):
        self.asked.setdefault(session_id, []).append(followup)

    def followups(self, session_id):
        return list(self.asked.get(session_id, []))

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

    assert [name for name, _ in events] == ["session", "intake", "plan", "lessons", "quiz", "done"]


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
    assert saved["rounds"] == []
    assert saved["waiting"]["round"] == 1
    assert len(saved["waiting"]["questions"]) == 2


def test_unknown_session_is_404(client):
    assert client.get(f"/sessions/{uuid.uuid4()}").status_code == 404


def ask(client, session_id, index, question):
    return client.post(f"/sessions/{session_id}/steps/{index}/ask", json={"question": question})


def test_deleting_a_session_removes_it_and_its_images(client, monkeypatch, tmp_path):
    monkeypatch.setattr("api.main.IMAGES_DIR", tmp_path)
    (tmp_path / "fake.png").write_bytes(b"png")
    session_id = dict(stream(client))["session"]["id"]

    assert client.delete(f"/sessions/{session_id}").status_code == 204

    assert client.get("/sessions").json() == []
    assert client.get(f"/sessions/{session_id}").status_code == 404
    assert not (tmp_path / "fake.png").exists()
    assert client.delete(f"/sessions/{session_id}").status_code == 404


def test_followup_is_answered_and_saved_with_the_session(client):
    session_id = dict(stream(client))["session"]["id"]

    response = ask(client, session_id, 1, "why does that work?")

    assert response.json() == {"index": 1, "question": "why does that work?", "answer": "more about step two"}
    assert client.get(f"/sessions/{session_id}").json()["followups"] == [response.json()]


def test_followup_sees_earlier_questions_on_the_same_step_only(client, fake_llm, monkeypatch):
    session_id = dict(stream(client))["session"]["id"]
    contents = []

    def spy(system, content, schema):
        contents.append(content)
        return fake_llm(system, content, schema)

    monkeypatch.setattr("tutor.llm.structured", spy)
    ask(client, session_id, 0, "first question")
    ask(client, session_id, 1, "other step question")
    ask(client, session_id, 0, "second question")

    assert "first question" not in contents[1]
    assert "Student asked: first question\nYou answered: more about step one" in contents[2]
    assert contents[2].endswith("New question: second question")
    followups = client.get(f"/sessions/{session_id}").json()["followups"]
    assert [(f["index"], f["question"]) for f in followups] == [
        (0, "first question"),
        (1, "other step question"),
        (0, "second question"),
    ]


def test_followup_on_unknown_session_or_step_is_404(client):
    session_id = dict(stream(client))["session"]["id"]

    assert ask(client, uuid.uuid4(), 0, "hi").status_code == 404
    assert ask(client, session_id, 5, "hi").status_code == 404


def test_empty_followup_is_rejected(client):
    session_id = dict(stream(client))["session"]["id"]

    assert ask(client, session_id, 0, "").status_code == 422


def submit(client, session_id, answers):
    response = client.post(f"/sessions/{session_id}/answers", json={"answers": answers})
    assert response.status_code == 200
    return parse_sse(response.text)


def test_quiz_event_hides_the_answers(client):
    quiz = dict(stream(client))["quiz"]

    assert quiz["round"] == 1
    assert [q["step"] for q in quiz["questions"]] == ["step one", "step two"]
    assert all("correct_answer" not in q for q in quiz["questions"])


def test_all_correct_answers_are_graded_and_finish(client):
    session_id = dict(stream(client))["session"]["id"]

    events = submit(client, session_id, ["right", "right"])

    assert [name for name, _ in events] == ["grade", "done"]
    grade = events[0][1]
    assert (grade["round"], grade["score"], grade["total"]) == (1, 2, 2)
    assert client.get(f"/sessions/{session_id}").json()["waiting"] is None


def test_missed_answer_streams_grade_reteach_and_next_quiz(client):
    session_id = dict(stream(client))["session"]["id"]

    events = submit(client, session_id, ["right", "wrong 1"])

    assert [name for name, _ in events] == ["grade", "reteach", "quiz", "done"]
    data = dict(events)
    assert data["grade"]["score"] == 1
    assert [a["correct_answer"] for a in data["grade"]["answers"]] == ["right", "right"]  # revealed only after grading
    [step] = data["reteach"]["steps"]
    assert (step["index"], step["step"], step["misconception"]) == (1, "step two", "thinks wrong 1")
    assert "question" not in step
    assert data["quiz"]["round"] == 2
    assert [q["question"] for q in data["quiz"]["questions"]] == ["retry question about step two?"]


def test_reopened_session_rebuilds_its_rounds(client):
    session_id = dict(stream(client))["session"]["id"]
    submit(client, session_id, ["right", "wrong 1"])

    saved = client.get(f"/sessions/{session_id}").json()

    [round_one] = saved["rounds"]
    assert round_one["grade"]["score"] == 1
    assert [s["index"] for s in round_one["reteach"]["steps"]] == [1]
    assert saved["waiting"]["round"] == 2


def test_answers_are_rejected_when_not_waiting_or_invalid(client):
    session_id = dict(stream(client))["session"]["id"]

    assert client.post(f"/sessions/{session_id}/answers", json={"answers": ["right"]}).status_code == 422
    assert client.post(f"/sessions/{session_id}/answers", json={"answers": ["right", "made up"]}).status_code == 422
    submit(client, session_id, ["right", "right"])
    assert client.post(f"/sessions/{session_id}/answers", json={"answers": ["right", "right"]}).status_code == 409
    assert client.post(f"/sessions/{uuid.uuid4()}/answers", json={"answers": []}).status_code == 404


def test_failed_answer_run_keeps_the_session(client, fake_llm):
    session_id = dict(stream(client))["session"]["id"]
    fake_llm.error = RuntimeError("gemini down")

    events = submit(client, session_id, ["wrong 1", "right"])  # the reteacher's call fails

    assert [name for name, _ in events] == ["grade", "error"]
    assert [s["id"] for s in client.get("/sessions").json()] == [session_id]
    assert client.get(f"/sessions/{session_id}").json()["stalled"] is True


def test_stalled_session_can_be_resumed(client, fake_llm):
    session_id = dict(stream(client))["session"]["id"]
    assert client.post(f"/sessions/{session_id}/resume").status_code == 409  # waiting for answers, not stalled
    fake_llm.error = RuntimeError("gemini down")
    submit(client, session_id, ["wrong 1", "right"])
    fake_llm.error = None

    response = client.post(f"/sessions/{session_id}/resume")

    assert [name for name, _ in parse_sse(response.text)] == ["reteach", "quiz", "done"]
    saved = client.get(f"/sessions/{session_id}").json()
    assert (saved["stalled"], saved["waiting"]["round"]) == (False, 2)


def test_followup_while_quiz_is_waiting_does_not_break_answering(client):
    session_id = dict(stream(client))["session"]["id"]
    ask(client, session_id, 0, "why?")

    events = submit(client, session_id, ["right", "wrong 2"])

    assert [name for name, _ in events] == ["grade", "reteach", "quiz", "done"]
    saved = client.get(f"/sessions/{session_id}").json()
    assert [f["question"] for f in saved["followups"]] == ["why?"]
    assert saved["waiting"]["round"] == 2
