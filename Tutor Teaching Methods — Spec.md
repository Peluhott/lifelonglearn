# Tutor Teaching Methods — Spec

Nov 3, 2026 · @jav

## Overview

The tutor moves from one fixed teaching flow to a set of teaching methods, each its own LangGraph subgraph, with a selection step that picks the method per request. The work ships in three phases, each usable on its own:

1. **Structured lesson subgraph:** the current teaching flow (teach each planned step, then quiz) moved into a subgraph. No behavior change.
2. **Socratic subgraph:** a second method that teaches through back-and-forth questions.
3. **Method selection:** a new node right after the planner picks structured or Socratic based on the topic and how the user asks for help.

Goal of this change: the tutor can teach the same concept in two different ways and choose sensibly between them. Measuring which method works better is a later phase and is not part of this spec.

## Target architecture

Today, one graph runs intake → planner → teacher × N in parallel → reviewer. The planner breaks the topic into steps, each teacher writes one step, and the reviewer writes the quiz. After this change, the parent graph only routes, and each teaching method is a subgraph that returns when the concept is done. Socratic pauses for the user with `interrupt()`; the structured lesson does not pause.

```
START → intake → planner → select_method ─┬─ structured_lesson (teacher × N → reviewer) ─┬→ END
                                          └─ socratic (question loop, pauses for answers) ─┘
```

Intake and the planner stay as they are; `select_method` is the only new parent node, and each method subgraph returns to the parent when it finishes.

## Phase 1: Structured lesson subgraph

Move the existing teaching flow into `tutor/methods/structured_lesson/` as a compiled subgraph that the parent graph adds as a node. From the user's side, nothing changes.

**Requirements**

1. `tutor/methods/structured_lesson/graph.py` exposes `build_graph()`, returning a compiled `StateGraph` (no checkpointer of its own; it inherits the parent's).
2. The subgraph contains the steps after the planner: teach every plan step in parallel with `Send`, then write the quiz with the reviewer. Breaking the topic into steps stays in the parent's planner, and a plan with no steps still skips teaching and review.
3. The existing quiz stays as it is: the reviewer writes multiple-choice questions and the browser grades them. Answers don't reach the backend, don't steer the lesson, and aren't used to score the method.
4. The subgraph has no interrupts. Interrupts are added in Phase 2, and the structured lesson doesn't use them.
5. The parent graph gets a `select_method` node that always chooses `"structured_lesson"` for now, and a conditional edge that routes on `state["select_method"].chosen_method`.
6. Methods are registered in `tutor/methods/__init__.py` as `METHODS = {"structured_lesson": build_graph}`; the parent adds a node and routing entry for each item in `METHODS`.
7. Prompts stay in `tutor/prompts/<name>.md`, loaded with `prompts.load(name)`; their wording stays the same.
8. `events()` in `api/main.py` streams with `subgraphs=True`, because otherwise a nested subgraph reports one `structured_lesson` update and the `lessons` and `review` SSE events stop. `subgraphs=True` yields `(namespace, update)` tuples, so the loop changes to match. SSE event names and payloads stay the same.

**Done when**

- [ ] A full lesson runs end to end with output equivalent to today's version, and SSE events still arrive as `session, intake, plan, lessons, review, done`.
- [ ] Saved sessions still reopen through `GET /sessions/{id}`.
- [ ] LangSmith shows the lesson as a nested run under the parent trace (needs a live Gemini run, so ask first).

## Phase 2: Socratic subgraph

Add `tutor/methods/socratic/`, a subgraph that leads the user to the key insight through one question at a time. Starts only after Phase 1 is done.

**Nodes** (all in `tutor/methods/socratic/nodes.py`)

1. `set_target`: writes the target insight (one or two sentences), the premises the reasoning needs, and common misconceptions to watch for. Internal only; never shown to the user.
2. `ask_question`: writes one question that builds on the user's last answer. The first question states any premise the user may not have (for example, "the network can lose messages").
3. `wait_for_answer`: pauses with `interrupt()` and stores the answer. It stays separate from the nodes that call the LLM because a node reruns from the top on resume, which would repeat and bill that call.
4. `evaluate_answer`: classifies the answer as `correct`, `partial`, `misconception`, or `stuck`, and sets `reached_target`, using structured output.
5. `give_hint`: writes a narrower question or a small hint, used after `stuck` or a repeated `partial` or `misconception`, then goes to `wait_for_answer`.
6. `wrap_up`: confirms the insight in plain words, then gives the terms the user couldn't derive (names, definitions).

**Loop rules**

- `correct` moves to the next step toward the target; `reached_target` goes to `wrap_up` and sets `outcome = "completed"`.
- A first `partial` or `misconception` gets a narrower question, never a direct correction.
- A repeated `partial` or `misconception` goes to `give_hint`.
- `stuck` goes to `give_hint`.
- Turn limit: after 99 questions without reaching the target, `wrap_up` explains the insight directly and sets `outcome = "stuck"`. Hints count as questions. 99 is a placeholder until the real limit is decided.
- Private state (`target_insight`, `premises`, `misconceptions`, `turns`, `misses`, `last_answer`, `evaluation`) stays inside the subgraph.
- The dialogue is kept in the shared `socratic` key, because private keys are gone from the parent state once the subgraph finishes and saved sessions need the dialogue to reopen.

**API, frontend, and CLI**

The graph can't reach a user without these changes, so they're part of this phase:

1. `POST /sessions/{id}/answer` continues an existing session with `Command(resume=...)` and the same `thread_id`. `POST /tutor/stream` always creates a new session. A failed resume keeps the session so the student can retry.
2. `events()` handles the `__interrupt__` update by sending a new `question` SSE event, doesn't send `done` while the graph is paused, and sends the ending as a new `wrap_up` event.
3. The frontend sends a reply into the current session during a dialogue. Today `send()` clears the screen and starts a new session on every message.
4. The `plan` SSE event is sent only for `structured_lesson`, after `select_method` has run. Otherwise a Socratic session shows the lesson pager and "Writing up the lessons…".
5. `GET /sessions/{id}` and the frontend rebuild a Socratic session from the `socratic` key. For a paused session, the parent state doesn't have the dialogue yet, so read it with `get_state(config, subgraphs=True)`.
6. `main.py` gets a checkpointer and a loop that reads answers. `tutor/graph.py::graph` has no checkpointer, so the CLI would stop at the first question with no error and no way to resume.

**Done when**

- [ ] A TCP handshake dialogue works end to end.
- [ ] A misconception gets a narrower question, not a correction.
- [ ] The turn limit ends the loop with a direct explanation.
- [ ] One question makes one LLM call, including after resume.
- [ ] A finished Socratic session and a paused one both reopen from the sidebar.
- [ ] Registered in `METHODS`; forcing `select_method` to choose `"socratic"` runs it with no other changes to the parent graph.

## Phase 3: Method selection

Replace the hardcoded `select_method` with an LLM call that reads the user's request and picks a method, using rules first and a default when unsure. It stays its own node right after the planner, so the planner's job (what to teach) stays separate from this one (how to teach it).

**Inputs:** `user_prompt`, the `intake` result (including `task_type` and `confusion_type`), and the `planner` result. There is no prerequisite check today and the planner doesn't change, so `select_method` judges from these inputs whether the user is missing prerequisites.

**Output (structured):** `chosen_method`, `request_type`, and a one-line `reason`, written to state as `select_method` and visible in LangSmith.

**Selection rules**

| Signal in the request | Example | Method |
| --- | --- | --- |
| New to the topic, wants an overview | "I'm new to this, give me an overview" | structured\_lesson |
| Stuck on one specific part | "I don't get why TCP needs three messages" | socratic |
| Topic is mostly told facts (syntax, names, definitions) | "What's the syntax for a list comprehension?" | structured\_lesson |
| Missing prerequisites for the confusing part | Stuck on a part, but the request shows the basics are missing | structured\_lesson |
| User names a style | "Just explain it" / "Ask me questions" | the one they named |
| Unclear | Anything else | structured\_lesson |

An explicit request from the user always wins over the other rules. `request_type` still records the underlying type of request when the user names a style.

**Done when**

- [ ] Each example prompt in the table routes to the listed method.
- [ ] Selection is a single `llm.structured` call. `llm.structured` already uses temperature 0, so no setting changes.
- [ ] `reason` appears in state and in the trace.
- [ ] Any error or unparseable output is caught inside the node and falls back to `structured_lesson`. An uncaught error would end the run and delete the session.

## Shared state and file structure

Every method subgraph reads and writes the same parent keys, so the parent never needs to know which method ran. A method's own state extends `TutorState` with private keys. State keys are named after the node that fills them.

| Key | Type | Set by | Purpose |
| --- | --- | --- | --- |
| `select_method` | SelectMethodResult | select\_method | `chosen_method` (which subgraph to route to), `request_type` (overview, specific\_confusion, told\_fact, unclear), `reason` (one line explaining the choice) |
| `socratic` | list of dialogue turns | socratic | The questions and answers, kept so saved sessions can reopen |
| `outcome` | str | each method | `completed` or `stuck` |

Existing state keys stay as they are; these are added alongside them. The existing keys already cover the rest: `user_prompt` holds the user's words, and `planner.concept_to_teach` holds what is being taught. `PlannerResult.method` stays too: it's free text passed to the teachers and is separate from `chosen_method`.

New Pydantic models go in `tutor/schemas.py`, because `db.serializer()` only allow-lists models defined there.

**Files added or moved in this change**

```
tutor/
├── graph.py                 # parent: intake → planner → select_method → [method] → END
├── state.py                 # TutorState (keys above + existing keys)
├── schemas.py               # SelectMethodResult, Socratic models
├── agents/
│   └── select_method.py     # Phase 1: hardcoded · Phase 3: LLM selection
├── prompts/                 # select_method.md, Socratic prompts
└── methods/
    ├── __init__.py          # METHODS registry
    ├── structured_lesson/   # Phase 1: teacher and reviewer move here
    │   ├── graph.py
    │   └── nodes.py
    └── socratic/            # Phase 2
        ├── graph.py
        └── nodes.py
```

## Out of scope

Do not build any of the following, even if it seems like a natural next step. Each is planned for a later phase.

**Measuring and learning which method works**

- No bandit, Thompson sampling, or any adaptive or learned method selection. Selection is rules plus one LLM call.
- No `learning_events` table, database schema, or event logging for method comparison.
- No LLM-as-judge, summary assessment, or scoring of how well a method worked.
- No `assessments/` folder, `select_assessment` node, or separate assessment subgraphs.
- No pretests, learning-gain calculation, or user preference ratings.
- No per-user or per-topic stats, and no `knowledge_type` or `domain` tags stored anywhere.

**Other teaching methods and features**

- No other methods: worked→faded, analogy bridging, productive failure, teach-back, and retrieval practice are later phases.
- No spaced repetition, review queue, or scheduled reviews.
- No new `explain` intent or quiz-skipping path. Intake's existing `explain_concept` task type stays, and "Just explain it" still gets the quiz.
- No switching between methods mid-lesson. A stuck Socratic run ends with a direct explanation inside its own subgraph and does not route to another method.
- No new tools (diagram generation, prereq lookup tools, and so on).

**Architecture and code**

- Stay on LangGraph. Do not migrate to LangChain agents, ReAct-style tool calling for methods, or another framework.
- Teaching methods are subgraphs, not tools an agent calls.
- Do not change models, providers, or model settings for existing nodes.
- Do not rename or restructure existing state keys, prompts, or nodes beyond what Phase 1 requires.
- Do not refactor unrelated parts of the app, change the UI beyond the Phase 2 list, or add caching, retries, or new dependencies unless a requirement above needs them.

## Open questions

- [x] What are the current state key names? `user_prompt`, `intake`, `planner`, `teacher`, `reviewer`. The shared-state table above is matched to them.
- [x] Is the planner an LLM call today, or partly rule-based? One LLM call with no rules. It has no prerequisite output, so `select_method` judges that itself.
- [ ] What should the real Socratic turn limit be, and should it be fixed or set per topic? It's 99 for now.
- [x] Does the existing quiz step use multiple-choice, open questions, or both? Multiple choice only: 4 choices per question, one question per step.
