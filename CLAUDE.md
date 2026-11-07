# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running

- CLI: `.venv/bin/python main.py` (reads a prompt from stdin, prints each node's result, then asks quiz rounds A–D or text prompts in the terminal)
- API: `uvicorn api.main:app --reload` (port 8000, which `frontend/src/api.js` expects). Needs Postgres at `DATABASE_URL`; startup creates the tables.
- Frontend: `cd frontend && npm run dev`; lint with `npm run lint` (oxlint). Plain JS, not TypeScript.
- Install: `.venv/bin/pip install -r requirements.txt`. Nothing is pinned.
- **Testing is handled by the user:** don't write, update, or run tests unless asked. This overrides the test steps in `/check` and the `add-graph-node` skill.
- Tests: `.venv/bin/python -m pytest -q` (offline). `tests/conftest.py` autouse-mocks `tutor.llm.structured` and `generate_image` and sets a fake `GEMINI_API_KEY` — tests must never call real Gemini. New schemas/nodes need a canned answer in `FakeLLM`. API tests swap in `InMemorySaver` + `FakeSessions` (no Postgres); only `tests/test_postgres.py` touches the real database and skips if it's unreachable.
- No Python linter/formatter. `/check` runs all offline verification.

**Ask before anything that calls Gemini** (running `main.py`, the API, the graph, or any node) — it costs money. Compiling, importing modules, and frontend lint are fine.

## Environment

- `.env`: `GEMINI_API_KEY`, `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `DATABASE_URL` (local Postgres, database `learning`).
- Read in code but not in `.env.example`: `LLM_MODEL` (default `gemini-3.5-flash`), `IMAGE_MODEL` (default `gemini-3.1-flash-image`). Frontend: `VITE_API_URL`.
- `load_dotenv()` runs only in `tutor/llm.py`; any module reading env vars must import `tutor.llm` first.

## Graph architecture

- Flow: intake → planner → select_method → one method subgraph → END, wired in `tutor/graph.py`. The parent adds a node and route for each entry in `METHODS` (`tutor/methods/__init__.py`), routing on `state["select_method"].chosen_method`.
- Parent nodes live in `tutor/agents/`; each method lives in `tutor/methods/<name>/` (`graph.py` with `build_graph()`, `nodes.py`). Subgraphs have no checkpointer of their own.
- `structured_lesson`: teacher × N **in parallel** → pick_check → check → finish. `teach_every_step` fans out one `Send("teacher", {"planner", "step_index"})` per plan step (or goes straight to `"finish"` if there are none); pick_check runs once after all teachers finish.
- `analogy_bridging`: analogy_lesson → pick_check → check → reexplain (only if `check_result.gaps`, once) → finish. The lesson is the shared `analogy_bridging` key.
- `worked_faded`: next_problem → ask_step → wait_for_step → evaluate_step → ask_step, next_problem, or faded_wrap_up. Keeps its own step checks. Private keys are in `WorkedFadedState`; the dialogue is the shared `worked_faded` key. A correction is carried in `carry` and opens the next tutor turn.
- Checks live in `tutor/checks/<name>/` and are registered in `CHECKS`; `add_checks(builder, next_node)` adds `pick_check` and every check to a method, so a check is nested two levels down. `socratic` and `worked_faded` don't use them. **Every check must set `output_schema=CheckOutput`:** one built on plain state hands back the method's whole `teacher` list and the reducer appends every lesson again. Each ends in a node named `check_result` writing a `CheckResult`.
- Text checks only `interrupt()` in `tutor/checks/context.py::wait_for_answer_node`, with `{"question": text}`, and keep their turns in the shared `check_turns` key. Read what was taught with `taught_steps()` / `taught_text()`, which cover teacher steps and analogy lessons. A planted mistake stays in private state, never in an interrupt payload.
- The `quiz` check is reviewer → grader ⇄ reteacher × missed → check_result; a step's newest answer decides whether it's a gap.
- **The graph pauses mid-run.** `grader_node` (plain Python, no LLM) calls `interrupt({round, questions})` with the quiz minus `correct_answer`; the run stops until it's resumed with `Command(resume=[one picked choice per question])`. On resume the grader re-runs from the top, so keep everything before `interrupt` side-effect free. Round 1 quizzes the reviewer's questions (index assigned by position); round N quizzes the questions written by round N-1's reteaches.
- `reteach_missed` sends one `Send("reteacher", ReteachTask)` per wrong answer in the latest round whose step has been retaught fewer than `MAX_RETEACHES` (2) times, else `"check_result"`. `reteacher → grader` waits for all of them, then quizzes again.
- `socratic`: set_target → ask_question → wait_for_answer → evaluate_answer → ask_question, give_hint, or wrap_up. Only `wait_for_answer` calls `interrupt()`, because a node reruns from the top on resume and an LLM call there would run twice. Private keys are in `SocraticState`; the dialogue is the shared `socratic` key. `MAX_TURNS` is a placeholder.
- `PlannerResult.hook` is the short opener shown on a structured lesson's first page in place of the steps. It defaults to `""` because older sessions were saved without it.
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

- Each session's id is also the graph's `thread_id`; `PostgresSaver` checkpoints the full graph state, so `GET /sessions/{id}` rebuilds a session with `graph.get_state(...)` (`.interrupts` holds a waiting quiz or Socratic question). Besides checkpoints there are two tables: `sessions` (the sidebar list: id, title, prompt, created_at) and `followups` (`ON DELETE CASCADE` from `sessions`).
- `tutor/graph.py::graph` uses an `InMemorySaver` (CLI, graph tests) because interrupts need a checkpointer, so always pass a `thread_id`. The API compiles its own with `build_graph(checkpointer)` in the lifespan.
- **A paused or failed subgraph's shared keys don't reach the parent until it finishes.** While a quiz waits, `teacher`, `reviewer`, `grader` and `reteacher` are only in the subgraph's state, so read a session with `get_state(config, subgraphs=True)` and `tutor/graph.py::method_values(snapshot)` (`state_of()` in `api/main.py`), never plain `.values`. The parent also keeps reporting an interrupt its subgraph has moved past, so read `.interrupts` from `live_snapshot(snapshot)`.
- Checkpoints store Pydantic objects; `tutor/serde.py::serializer()` (re-exported as `db.serializer`) allow-lists every model in `tutor/schemas.py` automatically. Models defined elsewhere must be added there or LangGraph will refuse to load them.
- No migration tool: tables are created with `CREATE TABLE IF NOT EXISTS` at startup.

## API streaming (`api/main.py`)

- `events()` runs or resumes the graph with `graph.stream(..., stream_mode="updates", subgraphs=True)` and turns updates into SSE events. Updates are `(namespace, update)` tuples, and a nested interrupt arrives once per graph level, so only the parent-level one is sent, as `quiz` if its payload has `questions` and `question` otherwise.
- First run (`POST /tutor/stream`): `session` (carries the id), `intake`, then what the method teaches (`plan` and `lessons`, or `analogy`) and the check after it (`quiz` or `question`), or a dialogue's first `question`, then `done`. `plan` is sent after `select_method` and only for `structured_lesson`. Quiz answers (`POST /sessions/{id}/answers`): `grade`, then `reteach` + `quiz` if anything was missed, `done`. Text answers (`POST /sessions/{id}/answer`): `question`, or at the end `wrap_up` (a dialogue) or `check_result`. A finished check sends `check_result`, then `reexplain` if an analogy lesson found gaps. `done` ends every stream, paused or not, so the frontend clears a dialogue on `wrap_up` and `check_result` instead; any stream can end in `error`.
- New nodes must not be named `intake`, `planner`, `select_method`, `wrap_up`, `faded_wrap_up`, `teacher`, `grader`, `reteacher`, `analogy_lesson`, `reexplain` or `check_result` unless they mean that event: `events()` matches node names at any depth.
- Only a failed **first** run deletes its session row and checkpoint thread. A failed answer run leaves the graph "stalled" (nodes left to run, no quiz waiting): `POST /sessions/{id}/resume` re-runs the failed tasks with `None` as input, and `/answer` does the same for a failed Socratic turn, keeping the answer already saved. Always resume by interrupt id (`resume_with()`): a plain `Command(resume=value)` stays in the parent checkpoint and would answer the next pause after a retry.
- Lessons and reteaches are buffered and each sent as one event.
- Errors are sent as an `error` event because the 200 response has already started.
- The generator is sync on purpose so FastAPI runs the blocking Gemini calls in a worker thread.
- Changing event names or payloads requires matching changes in `frontend/src/api.js`.
- Other routes: `GET /sessions`, `GET /sessions/{id}` (`method`, `plan`, `lessons`, `followups`, `rounds: [{grade, reteach}]`, `waiting` quiz or null, `stalled`, `socratic`, `worked_faded`, `check_turns`, `check_result`, `analogy_bridging`, `reexplain`, `in_progress`), `DELETE /sessions/{id}` (sidebar row + follow-ups, checkpoint thread, and the session's image files), `POST /sessions/{id}/steps/{index}/ask` (`{question}` → `{index, question, answer}`; calls Gemini). `/answers` returns 409 unless a quiz is waiting and 422 unless every answer is one of its question's choices; `/answer` returns 409 if a quiz is waiting or the session has finished.

## Conventions

- `learning.py` is a scratch script, not part of the app.
- In new code, comment only non-obvious logic; don't copy the line-by-line comment style of existing files.
