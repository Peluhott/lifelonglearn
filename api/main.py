import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api import db
from tutor.graph import build_graph
from tutor.schemas import TaughtStep
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


def sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event: a named event plus a JSON payload, ended by a blank line."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def lesson_payload(step: TaughtStep, total: int) -> dict:
    """One taught step as the frontend expects it; the frontend adds the API's address to image_url."""
    image_url = f"/images/{step.image}" if step.image else None
    return {"total": total, **step.model_dump(), "image_url": image_url}


def thread(session_id: uuid.UUID) -> dict:
    """Graph config that saves to / loads from this session's checkpoint thread."""
    return {"configurable": {"thread_id": str(session_id)}}


def events(graph, sessions, session_id: uuid.UUID, prompt: str):
    """Run the graph and yield SSE frames: session, intake, plan, all lessons in one chunk, then all questions in one chunk."""
    yield sse("session", {"id": str(session_id)})
    total = 0
    lessons = []  # taught steps are held here while the teachers run, then sent together
    try:
        # "updates" mode yields {node_name: what_that_node_returned} after every node runs
        for update in graph.stream({"user_prompt": prompt}, config=thread(session_id), stream_mode="updates"):
            for node, output in update.items():
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
                elif node == "reviewer" and output:  # reviewer returns {} (None here) when nothing was taught
                    yield sse("review", output["reviewer"].model_dump())
        if lessons:  # safety net in case the graph stops before the last step
            yield sse("lessons", {"lessons": sorted(lessons, key=lambda l: l["index"])})
        yield sse("done", {})
    except Exception as e:
        # a failed run isn't worth keeping in the sidebar
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
        events(request.app.state.graph, sessions, session_id, req.prompt),
        media_type="text/event-stream",
    )


@app.get("/sessions")
def list_sessions(request: Request) -> list[dict]:
    """Past sessions for the sidebar, newest first."""
    return request.app.state.sessions.list()


@app.get("/sessions/{session_id}")
def get_session(session_id: uuid.UUID, request: Request) -> dict:
    """Everything a finished session produced, rebuilt from its checkpoint."""
    values = request.app.state.graph.get_state(thread(session_id)).values
    if not values:
        raise HTTPException(status_code=404, detail="Session not found")
    plan = values.get("planner")
    taught = sorted(values.get("teacher", []), key=lambda t: t.index)
    review = values.get("reviewer")
    return {
        "id": str(session_id),
        "prompt": values["user_prompt"],
        "plan": plan.model_dump() if plan else None,
        "lessons": [lesson_payload(t, len(plan.steps)) for t in taught],
        "review": review.model_dump() if review else None,
    }
