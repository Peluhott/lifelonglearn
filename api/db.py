"""Postgres storage: LangGraph's checkpointer (full graph state per session) and the sessions list for the sidebar."""

import inspect
import os
import uuid

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from tutor import schemas
from tutor.schemas import FollowUp


def serializer() -> JsonPlusSerializer:
    """Checkpoint serializer allowed to rebuild every Pydantic model in tutor/schemas.py.

    LangGraph warns about (and will soon block) loading classes it wasn't told about,
    so new schema models are picked up here automatically.
    """
    models = [
        (schemas.__name__, name)
        for name, obj in vars(schemas).items()
        if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj.__module__ == schemas.__name__
    ]
    return JsonPlusSerializer(allowed_msgpack_modules=models)


def make_pool() -> ConnectionPool:
    """Connection pool for DATABASE_URL; open it with `with make_pool() as pool:`."""
    return ConnectionPool(
        os.environ["DATABASE_URL"],
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},  # settings PostgresSaver requires
        open=False,
    )


def postgres_checkpointer(pool: ConnectionPool) -> PostgresSaver:
    saver = PostgresSaver(pool, serde=serializer())
    saver.setup()  # creates LangGraph's checkpoint tables if they don't exist yet
    return saver


class PostgresSessions:
    """One row per tutoring session (the id is also the graph's thread_id), plus the follow-up questions asked in it.

    Follow-ups live here instead of the graph state: writing them into a checkpoint would cancel a quiz the graph is paused on.
    """

    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def setup(self) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id uuid PRIMARY KEY,
                    title text NOT NULL,
                    prompt text NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS followups (
                    id bigserial PRIMARY KEY,
                    session_id uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    step_index integer NOT NULL,
                    question text NOT NULL,
                    answer text NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )

    def create(self, session_id: uuid.UUID, prompt: str) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO sessions (id, title, prompt) VALUES (%s, %s, %s)",
                (session_id, prompt[:60], prompt),  # placeholder title until intake names the concept
            )

    def set_title(self, session_id: uuid.UUID, title: str) -> None:
        with self.pool.connection() as conn:
            conn.execute("UPDATE sessions SET title = %s WHERE id = %s", (title, session_id))

    def delete(self, session_id: uuid.UUID) -> bool:
        """Returns whether a row was there to delete."""
        with self.pool.connection() as conn:
            return conn.execute("DELETE FROM sessions WHERE id = %s", (session_id,)).rowcount > 0

    def add_followup(self, session_id: uuid.UUID, followup: FollowUp) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO followups (session_id, step_index, question, answer) VALUES (%s, %s, %s, %s)",
                (session_id, followup.index, followup.question, followup.answer),
            )

    def followups(self, session_id: uuid.UUID) -> list[FollowUp]:
        """Every follow-up asked in this session, in the order asked."""
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT step_index, question, answer FROM followups WHERE session_id = %s ORDER BY id", (session_id,)
            ).fetchall()
        return [FollowUp(index=r["step_index"], question=r["question"], answer=r["answer"]) for r in rows]

    def list(self) -> list[dict]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT id, title, created_at FROM sessions ORDER BY created_at DESC").fetchall()
        return [{"id": str(r["id"]), "title": r["title"], "created_at": r["created_at"].isoformat()} for r in rows]
