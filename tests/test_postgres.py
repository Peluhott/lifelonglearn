"""Round-trips a real checkpoint through the local Postgres in DATABASE_URL; skipped if it isn't reachable."""

import os
import uuid

import psycopg
import pytest

from api import db
from tutor.graph import build_graph
from tutor.schemas import FollowUp, PlannerResult, TaughtStep


def postgres_available():
    url = os.environ.get("DATABASE_URL")
    if not url:
        return False
    try:
        psycopg.connect(url, connect_timeout=2).close()
        return True
    except psycopg.OperationalError:
        return False


pytestmark = pytest.mark.skipif(not postgres_available(), reason="DATABASE_URL Postgres not reachable")


def test_graph_state_survives_a_round_trip_through_postgres(caplog):
    config = {"configurable": {"thread_id": f"test-{uuid.uuid4()}"}}
    with db.make_pool() as pool:
        saver = db.postgres_checkpointer(pool)
        try:
            build_graph(saver).invoke({"user_prompt": "help me with the chain rule"}, config=config)

            # a fresh graph on the same database, like after a server restart
            values = build_graph(db.postgres_checkpointer(pool)).get_state(config).values
        finally:
            saver.delete_thread(config["configurable"]["thread_id"])

    assert isinstance(values["planner"], PlannerResult)
    assert all(isinstance(t, TaughtStep) for t in values["teacher"])
    assert "unregistered type" not in caplog.text  # every schema model is allowed by db.serializer()


def test_followups_are_saved_and_deleted_with_their_session():
    session_id = uuid.uuid4()
    with db.make_pool() as pool:
        sessions = db.PostgresSessions(pool)
        sessions.setup()
        sessions.create(session_id, "test session")
        try:
            sessions.add_followup(session_id, FollowUp(index=1, question="why?", answer="because"))
            sessions.add_followup(session_id, FollowUp(index=0, question="how?", answer="like this"))
            assert [f.question for f in sessions.followups(session_id)] == ["why?", "how?"]
        finally:
            assert sessions.delete(session_id)
        assert sessions.followups(session_id) == []  # removed by ON DELETE CASCADE
        assert not sessions.delete(session_id)

