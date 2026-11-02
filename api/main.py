import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel, Field

from api import db
from tutor.agents.followup import answer_followup
from tutor.graph import build_graph
from tutor.schemas import FollowUp, GraderResult, RetaughtStep, TaughtStep
from tutor.tools.images import IMAGES_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open Postgres once at startup; every session's graph state is checkpointed there."""
    with db.make_pool() as pool:
        app.state.graph = build_graph(db.postgres_checkpointer(pool))
        app.state.sessions = db.PostgresSessions(pool)
        app.state.sessions.setup()
        yield


app = FastAPI(title="Tutor API", lifespan=lifespan)

# serve the teacher's generated images at /images/<file name>
IMAGES_DIR.mkdir(exist_ok=True)  # StaticFiles needs the folder to exist at startup
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")

# let a local frontend dev server call this API from the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TutorRequest(BaseModel):
    """What the frontend sends to start a tutoring session."""

    prompt: str = Field(min_length=1, description="What the student is stuck on.")


class AnswersRequest(BaseModel):
    """The student's pick for each question of the quiz the session is waiting on, in order."""

    answers: list[str]


class AskRequest(BaseModel):
    """A follow-up question about one lesson step."""

    question: str = Field(min_length=1)


def sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event: a named event plus a JSON payload, ended by a blank line."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def lesson_payload(step: TaughtStep, total: int) -> dict:
    """One taught step as the frontend expects it; the frontend adds the API's address to image_url."""
    image_url = f"/images/{step.image}" if step.image else None
    return {"total": total, **step.model_dump(), "image_url": image_url}


def grade_payload(result: GraderResult) -> dict:
    score = sum(a.is_correct for a in result.answers)
    return {**result.model_dump(), "score": score, "total": len(result.answers)}


def reteach_payload(retaught: list[RetaughtStep]) -> dict:
    # the new question isn't included: it's sent (without its answer) by the quiz that follows
    steps = sorted(retaught, key=lambda r: r.index)
    return {"steps": [r.model_dump(exclude={"question"}) for r in steps]}


def thread(session_id: uuid.UUID) -> dict:
    """Graph config that saves to / loads from this session's checkpoint thread."""
    return {"configurable": {"thread_id": str(session_id)}}


def events(graph, sessions, session_id: uuid.UUID, graph_input, first_run: bool):
    """Run (or resume) the graph and yield SSE frames until it finishes or pauses for quiz answers.

    First run: session, intake, plan, lessons (all at once), quiz. Answer runs: grade, then reteach + the next quiz
    if anything was missed. Every stream ends with done (or error).
    """
    if first_run:
        yield sse("session", {"id": str(session_id)})
    total = 0
    lessons = []  # taught steps are held here while the teachers run, then sent together
    retaught = []  # same for the parallel reteachers; sent when the next update (the quiz) arrives
    try:
        # "updates" mode yields {node_name: what_that_node_returned} after every node runs,
        # and {"__interrupt__": (Interrupt,)} when the grader pauses for answers
        for update in graph.stream(graph_input, config=thread(session_id), stream_mode="updates"):
            for node, output in update.items():
                if retaught and node != "reteacher":
                    yield sse("reteach", reteach_payload(retaught))
                    retaught = []
                if node == "intake":
                    intake = output["intake"]
                    if intake.target_concept:
                        sessions.set_title(session_id, intake.target_concept)
                    yield sse("intake", intake.model_dump())
                elif node == "planner":
                    plan = output["planner"]
                    total = len(plan.steps)  # remember how many steps so each lesson can say "2 of 5"
                    yield sse("plan", plan.model_dump())
                elif node == "teacher":
                    lessons.append(lesson_payload(output["teacher"][0], total))  # one update per parallel teacher
                    if len(lessons) == total:  # every step taught: send them all now, while the reviewer writes questions
                        yield sse("lessons", {"lessons": sorted(lessons, key=lambda l: l["index"])})
                        lessons = []
                elif node == "__interrupt__":
                    yield sse("quiz", output[0].value)  # the grader's payload: {round, questions without answers}
                elif node == "grader" and output:  # grader returns {} (None here) when there was nothing to quiz
                    yield sse("grade", grade_payload(output["grader"][0]))
                elif node == "reteacher":
                    retaught.append(output["reteacher"][0])
        if lessons:  # safety net in case the graph stops before the last step
            yield sse("lessons", {"lessons": sorted(lessons, key=lambda l: l["index"])})
        if retaught:
            yield sse("reteach", reteach_payload(retaught))
        yield sse("done", {})
    except Exception as e:
        if first_run:
            # a failed first run isn't worth keeping in the sidebar; a failed answer run keeps its lesson
            sessions.delete(session_id)
            if graph.checkpointer:
                graph.checkpointer.delete_thread(str(session_id))
        # the 200 response has already started by now, so errors have to be sent inside the stream
        yield sse("error", {"message": str(e)})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/tutor/stream")
def tutor_stream(req: TutorRequest, request: Request) -> StreamingResponse:
    session_id = uuid.uuid4()
    sessions = request.app.state.sessions
    sessions.create(session_id, req.prompt)
    # a regular (non-async) generator: FastAPI runs it in a worker thread, which suits the blocking Gemini calls
    return StreamingResponse(
        events(request.app.state.graph, sessions, session_id, {"user_prompt": req.prompt}, first_run=True),
        media_type="text/event-stream",
    )


@app.get("/sessions")
def list_sessions(request: Request) -> list[dict]:
    """Past sessions for the sidebar, newest first."""
    return request.app.state.sessions.list()


@app.get("/sessions/{session_id}")
def get_session(session_id: uuid.UUID, request: Request) -> dict:
    """Everything a session produced so far, rebuilt from its checkpoint."""
    snapshot = request.app.state.graph.get_state(thread(session_id))
    values = snapshot.values
    if not values:
        raise HTTPException(status_code=404, detail="Session not found")
    plan = values.get("planner")
    taught = sorted(values.get("teacher", []), key=lambda t: t.index)
    retaught = values.get("reteacher", [])
    return {
        "id": str(session_id),
        "prompt": values["user_prompt"],
        "plan": plan.model_dump() if plan else None,
        "lessons": [lesson_payload(t, len(plan.steps)) for t in taught],
        "followups": [f.model_dump() for f in request.app.state.sessions.followups(session_id)],
        # each graded quiz round and the reteaches it led to, in order
        "rounds": [
            {"grade": grade_payload(g), "reteach": reteach_payload([r for r in retaught if r.round == g.round])}
            for g in values.get("grader", [])
        ],
        "waiting": snapshot.interrupts[0].value if snapshot.interrupts else None,  # the quiz waiting for answers
        "stalled": stalled(snapshot),
    }


def stalled(snapshot) -> bool:
    """A run that failed part-way (e.g. a reteacher's Gemini call) leaves nodes to run but no quiz waiting."""
    return bool(snapshot.next) and not snapshot.interrupts


@app.post("/sessions/{session_id}/resume")
def resume_session(session_id: uuid.UUID, request: Request) -> StreamingResponse:
    """Retry the nodes a failed answer run didn't finish; streams like the answers route."""
    graph = request.app.state.graph
    snapshot = graph.get_state(thread(session_id))
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="Session not found")
    if not stalled(snapshot):
        raise HTTPException(status_code=409, detail="Nothing to resume")
    # None as input continues from the last checkpoint, re-running only the tasks that failed
    return StreamingResponse(
        events(graph, request.app.state.sessions, session_id, None, first_run=False),
        media_type="text/event-stream",
    )


@app.post("/sessions/{session_id}/answers")
def submit_answers(session_id: uuid.UUID, req: AnswersRequest, request: Request) -> StreamingResponse:
    """Resume the paused graph with the student's quiz answers and stream the grade (and any reteach + next quiz)."""
    graph = request.app.state.graph
    snapshot = graph.get_state(thread(session_id))
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="Session not found")
    if not snapshot.interrupts:
        raise HTTPException(status_code=409, detail="This session isn't waiting for quiz answers")
    questions = snapshot.interrupts[0].value["questions"]
    if len(req.answers) != len(questions) or any(a not in q["choices"] for a, q in zip(req.answers, questions)):
        raise HTTPException(status_code=422, detail="Pick one of the choices for every question")
    return StreamingResponse(
        events(graph, request.app.state.sessions, session_id, Command(resume=req.answers), first_run=False),
        media_type="text/event-stream",
    )


@app.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: uuid.UUID, request: Request) -> Response:
    """Remove a session from the sidebar along with its checkpoint and generated images."""
    graph = request.app.state.graph
    values = graph.get_state(thread(session_id)).values
    row_deleted = request.app.state.sessions.delete(session_id)
    if not values and not row_deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    for step in values.get("teacher", []):
        if step.image:
            (IMAGES_DIR / step.image).unlink(missing_ok=True)
    graph.checkpointer.delete_thread(str(session_id))
    return Response(status_code=204)


@app.post("/sessions/{session_id}/steps/{index}/ask")
def ask_about_step(session_id: uuid.UUID, index: int, req: AskRequest, request: Request) -> dict:
    """Answer a follow-up question about one taught step and save it with the session."""
    graph = request.app.state.graph
    config = thread(session_id)
    values = graph.get_state(config).values
    if not values:
        raise HTTPException(status_code=404, detail="Session not found")
    step = next((t for t in values.get("teacher", []) if t.index == index), None)
    if step is None:
        raise HTTPException(status_code=404, detail="Step not found")

    sessions = request.app.state.sessions
    earlier = [f for f in sessions.followups(session_id) if f.index == index]
    result = answer_followup(values["planner"], step, earlier, req.question)
    followup = FollowUp(index=index, question=req.question, answer=result.answer)
    sessions.add_followup(session_id, followup)
    return followup.model_dump()
