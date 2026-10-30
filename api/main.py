import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from tutor.graph import graph

app = FastAPI(title="Tutor API")

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


def events(prompt: str):
    """Run the graph and yield SSE frames: intake, plan, all lessons in one chunk, then all questions in one chunk."""
    total = 0
    lessons = []  # taught steps are held here while the teacher loops, then sent together
    try:
        # "updates" mode yields {node_name: what_that_node_returned} after every node runs
        for update in graph.stream(
            {"user_prompt": prompt},
            config={"recursion_limit": 50},  # each teacher step counts toward the limit
            stream_mode="updates",
        ):
            for node, output in update.items():
                if node == "intake":
                    yield sse("intake", output["intake"].model_dump())
                elif node == "planner":
                    plan = output["planner"]
                    total = len(plan.steps)  # remember how many steps so each lesson can say "2 of 5"
                    yield sse("plan", plan.model_dump())
                elif node == "teacher":
                    result = output["teacher"][0]  # teacher returns a one-item list so the state appends it
                    index = output["planner_index"] - 1  # teacher already moved the index past the step it taught
                    lessons.append({"index": index, "total": total, **result.model_dump()})
                    if index + 1 == total:  # last step taught: send every lesson now, while the reviewer writes questions
                        yield sse("lessons", {"lessons": lessons})
                        lessons = []
                elif node == "reviewer" and output:  # reviewer returns {} (None here) when nothing was taught
                    yield sse("review", output["reviewer"].model_dump())
        if lessons:  # safety net in case the graph stops before the last step
            yield sse("lessons", {"lessons": lessons})
        yield sse("done", {})
    except Exception as e:
        # the 200 response has already started by now, so errors have to be sent inside the stream
        yield sse("error", {"message": str(e)})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/tutor/stream")
def tutor_stream(req: TutorRequest) -> StreamingResponse:
    # a regular (non-async) generator: FastAPI runs it in a worker thread, which suits the blocking Gemini calls
    return StreamingResponse(events(req.prompt), media_type="text/event-stream")
