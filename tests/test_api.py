import json

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
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

    assert [name for name, _ in events] == ["intake", "plan", "lessons", "review", "done"]


def test_lessons_event_holds_every_step_with_image_urls(client):
    lessons = dict(stream(client))["lessons"]["lessons"]

    assert [(l["index"], l["total"], l["step"]) for l in lessons] == [(0, 2, "step one"), (1, 2, "step two")]
    assert lessons[0]["image_url"] == "/images/fake.png"
    assert lessons[1]["image_url"] is None


def test_llm_failure_becomes_error_event(client, fake_llm):
    fake_llm.error = RuntimeError("gemini down")

    events = stream(client)

    assert events == [("error", {"message": "gemini down"})]


def test_empty_prompt_is_rejected(client):
    response = client.post("/tutor/stream", json={"prompt": ""})

    assert response.status_code == 422
