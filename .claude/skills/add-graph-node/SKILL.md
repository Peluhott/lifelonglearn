---
name: add-graph-node
description: Checklist for adding a new agent node to the LangGraph tutor (schema, state key, prompt, node function, graph wiring, API SSE event, frontend). Use when adding or splitting an agent in tutor/agents/.
---

Read `tutor/agents/reviewer.py` (single call) and `tutor/agents/teacher.py` (looping node) first and mirror their shape.

1. **Schema** — add a Pydantic result model to `tutor/schemas.py`. If the code needs to attach fields the model shouldn't fill, subclass it (like `TeacherResult` → `TaughtStep`) and pass only the base class to `structured`.
2. **State** — add a key named after the node to `TutorState` in `tutor/state.py`. If the node runs in a loop and must accumulate, use `Annotated[list[X], operator.add]` and return a one-item list per run.
3. **Prompt** — write `tutor/prompts/<name>.md`.
4. **Node** — create `tutor/agents/<name>.py`:
   - `<NAME>_INSTRUCTIONS = prompts.load("<name>")` at module level
   - `def <name>_node(state: TutorState) -> dict:` calling `llm.structured(system=..., content=..., schema=...)` and returning `{"<name>": result}`
5. **Wire** — in `tutor/graph.py`, `add_node` and its edges. If it adds steps to a loop, check that `recursion_limit=50` (set in `main.py` and `api/main.py`) still covers the longest plan.
6. **API** — add a branch in `events()` in `api/main.py` that yields an SSE event for the node's output. Handle empty `{}` outputs (a node that returns nothing yields no key).
7. **Frontend** — handle the new event in `frontend/src/api.js` and render it in the UI.
8. **CLI** — print the new key in `main.py` if it should appear there.
9. **Tests** — add a canned answer for the new schema to `FakeLLM` in `tests/conftest.py`, then extend the expected call order in `tests/test_graph.py` and the event order in `tests/test_api.py`.
10. Run `/check`. Ask before any live run.
