"""Round-trips real checkpoints and session rows through the Postgres in DATABASE_URL; skipped if it isn't reachable."""

import os
import uuid

import psycopg
import pytest

from api import db
from tutor.graph import build_graph
from langgraph.types import Command

from tutor.schemas import FollowUp, GraderResult, PlannerResult, RetaughtStep, TaughtStep


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
            graph = build_graph(saver)
            graph.invoke({"user_prompt": "help me with the chain rule"}, config=config)  # pauses for quiz answers
            graph.invoke(Command(resume=["right", "wrong 1"]), config=config)  # pauses again for the retry quiz

            # a fresh graph on the same database, like after a server restart
            snapshot = build_graph(db.postgres_checkpointer(pool)).get_state(config)
        finally:
            saver.delete_thread(config["configurable"]["thread_id"])

    values = snapshot.values
    assert isinstance(values["planner"], PlannerResult)
    assert all(isinstance(t, TaughtStep) for t in values["teacher"])
    assert [type(g) for g in values["grader"]] == [GraderResult]
    assert [type(r) for r in values["reteacher"]] == [RetaughtStep]
    assert snapshot.interrupts[0].value["round"] == 2
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
