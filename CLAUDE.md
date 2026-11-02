# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running

- CLI: `.venv/bin/python main.py` (reads a prompt from stdin, prints each node's result, then asks the quiz rounds A–D in the terminal)
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

- Flow: intake → planner → teacher × N **in parallel** → reviewer → grader ⇄ reteacher × missed → END, wired in `tutor/graph.py`. `teach_every_step` fans out one `Send("teacher", {"planner", "step_index"})` per plan step (or goes straight to `"reviewer"` if there are none); the reviewer runs once after all teachers finish.
- **The graph pauses mid-run.** `grader_node` (plain Python, no LLM) calls `interrupt({round, questions})` with the quiz minus `correct_answer`; the run stops until it's resumed with `Command(resume=[one picked choice per question])`. On resume the grader re-runs from the top, so keep everything before `interrupt` side-effect free. Round 1 quizzes the reviewer's questions (index assigned by position); round N quizzes the questions written by round N-1's reteaches.
- `reteach_missed` sends one `Send("reteacher", ReteachTask)` per wrong answer in the latest round whose step has been retaught fewer than `MAX_RETEACHES` (2) times, else `END`. `reteacher → grader` waits for all of them, then quizzes again.
- `teacher_node` and `reteacher_node` receive a `TeacherTask` / `ReteachTask` (`tutor/state.py`), not the shared state.
- State keys in `tutor/state.py` are named after the node that fills them.
- `teacher`, `grader` and `reteacher` are `Annotated[list[...], operator.add]`, so those nodes return a **one-item list**. Parallel teachers/reteachers finish in any order: always sort by `.index` before showing or using them. With a reducer the key reads as `[]` before anything is added, never missing.
- All LLM calls go through `tutor/llm.py::structured(system, content, schema)` — don't call the Gemini client directly for text.
- Prompts are `tutor/prompts/<name>.md`, loaded via `prompts.load(name)` into a module-level `<NAME>_INSTRUCTIONS`.
- `TeacherResult` / `ReteachResult` are the schemas the model fills; `TaughtStep` / `RetaughtStep` subclass them to add fields the model never sees (`image`, `index`, `round`).
- `reviewer_node` returns `{}` when nothing was taught; `grader_node` returns `{}` (without interrupting) when there's nothing to quiz.
- Follow-up questions about a step are answered outside the graph by `tutor/agents/followup.py::answer_followup` (prompt `followup.md`) and stored in the `followups` table, **not** graph state: writing a checkpoint with `update_state` while the grader is paused drops the pending interrupt.

## Images

`tutor/tools/images.py` writes to `generated_images/` (git-ignored) and returns only the file name. `api/main.py` turns it into `/images/<name>`; the frontend prefixes `API_URL`. Image failures are caught in `teacher_node` so the lesson continues.

## Persistence (`api/db.py`)

- Each session's id is also the graph's `thread_id`; `PostgresSaver` checkpoints the full graph state, so `GET /sessions/{id}` rebuilds a session with `graph.get_state(...)` (`.interrupts` holds a waiting quiz). Besides checkpoints there are two tables: `sessions` (the sidebar list: id, title, prompt, created_at) and `followups` (`ON DELETE CASCADE` from `sessions`).
- `tutor/graph.py::graph` uses an `InMemorySaver` (CLI, graph tests) because interrupts need a checkpointer, so always pass a `thread_id`. The API compiles its own with `build_graph(checkpointer)` in the lifespan.
- Checkpoints store Pydantic objects; `tutor/serde.py::serializer()` (re-exported as `db.serializer`) allow-lists every model in `tutor/schemas.py` automatically. Models defined elsewhere must be added there or LangGraph will refuse to load them.
- No migration tool: tables are created with `CREATE TABLE IF NOT EXISTS` at startup.

## API streaming (`api/main.py`)

- `events()` runs or resumes the graph with `graph.stream(..., stream_mode="updates")` and turns updates into SSE events. First run (`POST /tutor/stream`): `session` (carries the id), `intake`, `plan`, `lessons`, `quiz` (from the `__interrupt__` update), `done`. Answer runs (`POST /sessions/{id}/answers`): `grade`, then `reteach` + `quiz` if anything was missed, `done`. Any stream can end in `error`.
- Only a failed **first** run deletes its session row and checkpoint thread. A failed answer run leaves the graph "stalled" (nodes left to run, no quiz waiting); `POST /sessions/{id}/resume` re-runs the failed tasks with `None` as input.
- Lessons and reteaches are buffered and each sent as one event.
- Errors are sent as an `error` event because the 200 response has already started.
- The generator is sync on purpose so FastAPI runs the blocking Gemini calls in a worker thread.
- Changing event names or payloads requires matching changes in `frontend/src/api.js`.
- Other routes: `GET /sessions`, `GET /sessions/{id}` (`plan`, `lessons`, `followups`, `rounds: [{grade, reteach}]`, `waiting` quiz or null, `stalled`), `DELETE /sessions/{id}` (sidebar row + follow-ups, checkpoint thread, and the session's image files), `POST /sessions/{id}/steps/{index}/ask` (`{question}` → `{index, question, answer}`; calls Gemini). `/answers` returns 409 when the session isn't waiting and 422 unless every answer is one of its question's choices.

## Conventions

- `learning.py` is a scratch script, not part of the app.
- In new code, comment only non-obvious logic; don't copy the line-by-line comment style of existing files.
