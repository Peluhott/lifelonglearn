"""Postgres storage: LangGraph's checkpointer (full graph state per session), the sessions list for the sidebar, and
the learning episodes that track how each session went."""

import os
import uuid

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from tutor.schemas import FollowUp
from tutor.serde import serializer  # re-exported: tests and the API use db.serializer()


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
            # no foreign key to sessions: deleting a lesson from the sidebar keeps its learning history
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_episodes (
                    session_id uuid PRIMARY KEY,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    subject text NOT NULL,
                    topic text NOT NULL,
                    teaching_method text NOT NULL,
                    request_type text NOT NULL,
                    task_type text NOT NULL,
                    testing_method text,
                    outcome text,
                    finished_at timestamptz,
                    score real,
                    score_detail jsonb,
                    rubric_version integer,
                    judge_model text,
                    liked boolean,
                    liked_reason text
                )
                """
            )
            conn.execute("ALTER TABLE learning_episodes ADD COLUMN IF NOT EXISTS pick_reason text")

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

    def start_episode(
        self,
        session_id: uuid.UUID,
        subject: str,
        topic: str,
        teaching_method: str,
        request_type: str,
        task_type: str,
        pick_reason: str,
    ) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO learning_episodes
                    (session_id, subject, topic, teaching_method, request_type, task_type, pick_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (session_id) DO NOTHING
                """,
                (session_id, subject, topic, teaching_method, request_type, task_type, pick_reason),
            )

    def delete_episode(self, session_id: uuid.UUID) -> None:
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM learning_episodes WHERE session_id = %s", (session_id,))

    def finish_episode(self, session_id: uuid.UUID, testing_method: str | None, outcome: str | None) -> bool:
        """Returns whether this call finished it, so a session is only ever scored once."""
        with self.pool.connection() as conn:
            return (
                conn.execute(
                    """
                    UPDATE learning_episodes SET testing_method = %s, outcome = %s, finished_at = now()
                    WHERE session_id = %s AND finished_at IS NULL
                    """,
                    (testing_method, outcome, session_id),
                ).rowcount
                > 0
            )

    def set_score(
        self,
        session_id: uuid.UUID,
        score: float,
        detail: dict | None = None,
        rubric_version: int | None = None,
        judge_model: str | None = None,
    ) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                UPDATE learning_episodes SET score = %s, score_detail = %s, rubric_version = %s, judge_model = %s
                WHERE session_id = %s
                """,
                (score, Jsonb(detail) if detail else None, rubric_version, judge_model, session_id),
            )

    def set_feedback(self, session_id: uuid.UUID, liked: bool, reason: str | None) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE learning_episodes SET liked = %s, liked_reason = %s WHERE session_id = %s",
                (liked, reason, session_id),
            )

    def episode(self, session_id: uuid.UUID) -> dict | None:
        """The student's rating for this session; None for sessions from before episodes existed."""
        with self.pool.connection() as conn:
            return conn.execute(
                "SELECT liked, liked_reason FROM learning_episodes WHERE session_id = %s", (session_id,)
            ).fetchone()

    def recent_episodes(self, limit: int = 500) -> list[dict]:
        """Past episodes, newest first, in the plain form tutor/history.py reads; they go into the graph's input."""
        with self.pool.connection() as conn:
            return conn.execute(
                """
                SELECT subject, teaching_method, request_type, testing_method, score, liked, liked_reason,
                       finished_at IS NOT NULL AS finished
                FROM learning_episodes ORDER BY created_at DESC LIMIT %s
                """,
                (limit,),
            ).fetchall()

    def method_report(
        self, subject: str | None = None, request_type: str | None = None, pick_reason: str | None = None
    ) -> dict:
        """How each teaching method has gone. Scores are grouped by test type because they aren't comparable across types.

        Finish rate is reported on its own: an abandoned session has no test type, so inside a test group it'd always be 100%.
        """
        params = {"subject": subject, "request_type": request_type, "pick_reason": pick_reason}
        matching = " AND ".join(f"(%({key})s::text IS NULL OR {key} = %({key})s)" for key in params)
        with self.pool.connection() as conn:
            by_test = conn.execute(
                f"""
                SELECT COALESCE(testing_method, 'none') AS testing_method, teaching_method,
                       count(*) AS sessions, avg(score)::float AS avg_score, avg(liked::int)::float AS thumbs_up_rate
                FROM learning_episodes
                WHERE finished_at IS NOT NULL AND {matching}
                GROUP BY 1, 2 ORDER BY 1, 2
                """,
                params,
            ).fetchall()
            by_method = conn.execute(
                f"""
                SELECT teaching_method, count(*) AS sessions, count(finished_at)::float / count(*) AS finish_rate
                FROM learning_episodes
                WHERE {matching}
                GROUP BY 1 ORDER BY 1
                """,
                params,
            ).fetchall()
        return {"by_test": by_test, "by_method": by_method}

    def list(self) -> list[dict]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT id, title, created_at FROM sessions ORDER BY created_at DESC").fetchall()
        return [{"id": str(r["id"]), "title": r["title"], "created_at": r["created_at"].isoformat()} for r in rows]
