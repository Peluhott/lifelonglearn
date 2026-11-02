# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running

- CLI: `.venv/bin/python main.py` (reads a prompt from stdin, prints each node's result)
- API: `uvicorn api.main:app --reload` (port 8000, which `frontend/src/api.js` expects). Needs Postgres at `DATABASE_URL`; startup creates the tables.
- Frontend: `cd frontend && npm run dev`; lint with `npm run lint` (oxlint). Plain JS, not TypeScript.
- Install: `.venv/bin/pip install -r requirements.txt`. Nothing is pinned.
- Tests: `.venv/bin/python -m pytest -q` (offline; run after changes). `tests/conftest.py` autouse-mocks `tutor.llm.structured` and `generate_image` and sets a fake `GEMINI_API_KEY` — tests must never call real Gemini. When adding a schema/node, add its canned answer to `FakeLLM`. API tests swap in `InMemorySaver` + `FakeSessions` (no Postgres); only `tests/test_postgres.py` touches the real database and skips if it's unreachable.
- No Python linter/formatter. `/check` runs all offline verification.

**Ask before anything that calls Gemini** (running `main.py`, the API, the graph, or any node) — it costs money. Compiling, importing modules, and frontend lint are fine.

## Environment

- `.env`: `GEMINI_API_KEY`, `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `DATABASE_URL` (local Postgres, database `learning`).
- Read in code but not in `.env.example`: `LLM_MODEL` (default `gemini-3.5-flash`), `IMAGE_MODEL` (default `gemini-3.1-flash-image`). Frontend: `VITE_API_URL`.
- `load_dotenv()` runs only in `tutor/llm.py`; any module reading env vars must import `tutor.llm` first.

## Graph architecture

- Flow: intake → planner → teacher × N **in parallel** → reviewer, wired in `tutor/graph.py`. `teach_every_step` fans out one `Send("teacher", {"planner", "step_index"})` per plan step (or goes straight to `"reviewer"` if there are none); the reviewer runs once after all teachers finish.
- `teacher_node` receives a `TeacherTask` (`tutor/state.py`), not the shared state.
- State keys in `tutor/state.py` are named after the node that fills them.
- `teacher` is `Annotated[list[TaughtStep], operator.add]`, so `teacher_node` must return a **one-item list**. Parallel teachers finish in any order: always sort by `TaughtStep.index` before showing or using them.
- All LLM calls go through `tutor/llm.py::structured(system, content, schema)` — don't call the Gemini client directly for text.
- Prompts are `tutor/prompts/<name>.md`, loaded via `prompts.load(name)` into a module-level `<NAME>_INSTRUCTIONS`.
- `TeacherResult` is the schema the model fills; `TaughtStep` subclasses it to add `image`, which the model never sees.
- `reviewer_node` returns `{}` when nothing was taught.

## Images

`tutor/tools/images.py` writes to `generated_images/` (git-ignored) and returns only the file name. `api/main.py` turns it into `/images/<name>`; the frontend prefixes `API_URL`. Image failures are caught in `teacher_node` so the lesson continues.

## Persistence (`api/db.py`)

- Each session's id is also the graph's `thread_id`; `PostgresSaver` checkpoints the full graph state, so `GET /sessions/{id}` rebuilds a session with `graph.get_state(...)`. The `sessions` table only holds the sidebar list (id, title, prompt, created_at).
- `tutor/graph.py::graph` has no checkpointer (CLI, graph tests); the API compiles its own with `build_graph(checkpointer)` in the lifespan.
- Checkpoints store Pydantic objects; `db.serializer()` allow-lists every model in `tutor/schemas.py` automatically. Models defined elsewhere must be added there or LangGraph will refuse to load them.
- No migration tool: tables are created with `CREATE TABLE IF NOT EXISTS` at startup.

## API streaming (`api/main.py`)

- `graph.stream(..., stream_mode="updates")` → SSE events `session` (always first, carries the id), `intake`, `plan`, `lessons`, `review`, `done`, `error`. A failed run deletes its session row and checkpoint thread.
- Lessons are buffered and sent as one `lessons` event after the last step.
- Errors are sent as an `error` event because the 200 response has already started.
- The generator is sync on purpose so FastAPI runs the blocking Gemini calls in a worker thread.
- Changing event names or payloads requires matching changes in `frontend/src/api.js`.

## Conventions

- `learning.py` is a scratch script, not part of the app.
- In new code, comment only non-obvious logic; don't copy the line-by-line comment style of existing files.
