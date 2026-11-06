# Tutor Methods & Checks — Spec

Nov 5, 2026 · @jav

## Overview

Add two teaching methods (`worked_faded`, `analogy_bridging`) and a shared set of four understanding checks (`quiz`, `retrieval_practice`, `teach_back`, `erroneous_examples`). Follow the existing pattern: each method and each check is its own LangGraph subgraph, registered in a dict and routed to by name.

| Teaching method | How it checks understanding |
| --- | --- |
| `structured_lesson` (exists) | Picks one shared check |
| `socratic` (exists) | Keeps its own built-in checks; no change |
| `worked_faded` (new) | Keeps its own built-in step checks |
| `analogy_bridging` (new) | Picks one shared check |

Before starting, read how `structured_lesson` and `socratic` are built and match their conventions for state, prompts, interrupts, and registration.

**This reverses two rules from the Teaching Methods spec.** The structured lesson now pauses with `interrupt()`, and quiz answers now reach the backend. Today the quiz has no interrupt, the browser grades it, and nothing uses the results.

## New teaching methods

### worked\_faded

Teaches a procedure by showing a solved problem, then giving similar problems with more steps left to the user each time.

1. `next_problem` writes one problem at a time, so the number of variants always matches the problem limit. Each problem has 3 or 4 steps, and every variant keeps the first problem's step structure.
2. Show the first problem fully solved, each step explained, and ask the user one "why does this step work?" question. The answer gets one line of feedback and doesn't change the level.
3. Each next problem shows the solved steps except the last N, which the user completes. N starts at 1 and grows by one per problem (remove steps from the end first).
4. Check each step as the user submits it, not the whole answer at the end. The first wrong step ends that problem.
5. Correct: next problem leaves one more step to the user. Wrong: show the correct step, count one miss, then repeat the same level with a new variant. Two misses in a row: go back one level and reset `misses`. N never goes below 1.
6. Finish when the user solves a full problem alone (`outcome = "completed"`), or after 6 problems (`outcome = "stuck"`, end with a direct walkthrough). The worked example counts as problem 1, so with 4 steps a perfect run reaches the full problem at problem 5.

Uses its own step checks only, not the shared checks.

**Rules**

- Models in `tutor/schemas.py`: `FadedProblem` (the problem and its solved steps) and `StepEvaluation` (`correct`, `feedback`).
- Private keys stay in a `WorkedFadedState`, like `SocraticState`: the current problem, `level`, `problems_seen`, `step_index`, `misses`, `last_answer`.
- The dialogue is kept in a shared `worked_faded` key, a list of `DialogueTurn` with `operator.add`, so saved sessions can reopen.
- Only a wait node calls `interrupt()`, with `{"question": text}`. A correction is part of the next tutor turn.
- The last node is `faded_wrap_up`, not `wrap_up` (see "Node names" below).
- Prompts write math and code as plain text, because the frontend only renders text.

### analogy\_bridging

Teaches an abstract concept by mapping it onto something familiar.

1. Pick an analogy from an everyday domain the user is likely to know.
2. Explain the concept through the analogy, then list the mapping explicitly (this part of the analogy = this part of the concept).
3. Explain where the analogy breaks down, so the user doesn't carry over wrong ideas.
4. Run one shared check (see the next section).
5. If the check finds gaps, `reexplain` covers them once, and the model chooses between using the mapping and trying one different analogy. There is no second check. Then finish.

**Rules**

- Steps 1 to 3 are one structured call that returns `AnalogyLesson` (`analogy`, `explanation`, `mapping`, `limits`), stored in a shared `analogy_bridging` key.
- `reexplain` writes its text to a shared `reexplain` key.
- `outcome` is `"completed"` if the check passed and `"stuck"` if it found gaps.

## Understanding checks

Four shared checks, each its own subgraph in `tutor/checks/`, registered in `tutor/checks/__init__.py` as a `CHECKS` dict. Each one pauses for the user with `interrupt()` and writes the same result to state. As in `socratic`, only a wait node with no LLM call calls `interrupt()`, because a node reruns from the top on resume.

```python
class CheckResult(BaseModel):  # in tutor/schemas.py, so db.serializer() can load it
    check_type: str
    passed: bool
    gaps: list[str]
```

**Check subgraphs must set `output_schema`, limited to `check_result`, `check_turns`, and `reviewer`.** `teacher` uses an `operator.add` reducer. A check built on plain `TutorState` returns the whole `teacher` list when it finishes, and the method appends it again, so every lesson is duplicated. An offline test on LangGraph 1.2.17 gave `[1, 2, 1, 2]` without `output_schema` and `[1, 2]` with it.

**What checks read.** Use `tutor/checks/context.py::taught_text(state)` for what was just taught. It reads `teacher` sorted by `index`, or `analogy_bridging`, because an analogy lesson has no `teacher` steps.

| Check | What the user does | How it's evaluated |
| --- | --- | --- |
| `quiz` | Answers multiple choice questions. Each answer is shown as it's picked, as today, then all picks are sent at once. | `grade_quiz` compares each pick to `correct_answer`, with no LLM call. `gaps` is the step of each missed question, and `passed` means no gaps. |
| `retrieval_practice` | Writes down the key points from memory without looking back. | Compares the answer to `taught_text` and lists what's missing. No separate key points are generated. |
| `teach_back` | Explains the concept to the AI, which plays a confused student and asks 1 to 3 naive follow-up questions. | `MAX_FOLLOW_UPS = 3`. The model returns a follow-up or stops, then one evaluation covers the whole exchange. |
| `erroneous_examples` | Gets a solution or explanation with one planted mistake (a common misconception), then finds and fixes it. | Compares the answer to the planted mistake, which stays in private state and never goes in the interrupt payload. |

**Moving the quiz.** Keep the `reviewer` node, `reviewer` state key, `reviewer.md` prompt, and `review` SSE event, so the existing frontend and saved sessions keep working. Add a wait node and `grade_quiz` after it. For an analogy lesson, the explanation, mapping, and limits count as the three steps.

**Dialogue.** Text checks add their turns to a shared `check_turns` key, a list of `DialogueTurn` with `operator.add`, so checks reopen from the sidebar.

**Picking a check.** `structured_lesson` and `analogy_bridging` each get a `pick_check` node that runs before checking understanding:

- One LLM call with structured output that returns `PickCheckResult` (`check`, a `Literal` of the names in `CHECKS`, and `reason`), stored in a `pick_check` state key. `reason` then shows in LangSmith the same way `select_method.reason` does.
- Prompt: given the concept and what was just taught, pick the check that will most effectively show whether the user understood it.
- Route to that check's subgraph, then back into the teaching method. `add_checks(builder, next_node)` in `tutor/checks/__init__.py` adds each check and its edge, so both methods wire them the same way.
- `structured_lesson` runs teacher × N → `pick_check` → check → `finish`. It shows the gaps in a closing message and sets `outcome = "completed"`. It doesn't re-explain.
- `analogy_bridging` goes to `reexplain` when `check_result.gaps` isn't empty, and otherwise to `finish`.
- A plan with no steps skips `pick_check` and goes straight to `finish`.
- Any error falls back to `quiz`, caught inside the node like `select_method_node`. An uncaught error on a first run deletes the session.

`socratic` and `worked_faded` do not use `pick_check` or the shared checks.

## Method selection updates

Register both new methods in `METHODS`. Add them to `SelectMethodResult.chosen_method`, add `procedure` and `abstract_concept` to `request_type`, and update `tutor/prompts/select_method.md`.

The rules replace the current list. Apply them in order and stop at the first one that fits:

| # | Signal in the request | Example | Method |
| --- | --- | --- | --- |
| 1 | User names a style | "Just explain it" / "Ask me questions" / "Walk me through an example" / "Give me an analogy" | the one they named |
| 2 | Topic is mostly told facts (syntax, names, definitions) | "What's the syntax for a list comprehension?" | `structured_lesson` |
| 3 | Wants to learn to do a multi-step procedure | "How do I solve recurrence relations?" | `worked_faded` |
| 3 | Can't do a kind of problem | "I keep getting these Big-O problems wrong" | `worked_faded` |
| 4 | Stuck, but missing specific prerequisites | Stuck on a part, but the request shows the basics are missing | `structured_lesson` |
| 5 | Concept feels abstract, and the user has no mental model for it | "Pointers make no sense to me" | `analogy_bridging` |
| 6 | Stuck on one specific part | "I don't get why TCP needs three messages" | `socratic` |
| 7 | New to the topic, or anything else | "I'm new to this, give me an overview" | `structured_lesson` |

The user naming a style still wins, and `structured_lesson` stays the default when unclear.

## API, frontend, and CLI

The graph can't reach a user without these changes, so they're part of this work.

**API (`api/main.py`)**

1. `AnswerRequest.answer` becomes `str | list[str]`, so quiz picks can be sent together.
2. `events()` sends `question` only when the interrupt payload has one. The quiz's pause sends nothing, because the `review` event already delivered its questions, but it still counts as paused so `done` isn't sent.
3. New SSE events: `analogy` (the `AnalogyLesson`), `reexplain` (`{"text": ...}`), and `check_result` (the `CheckResult`). `faded_wrap_up` sends the existing `wrap_up` event, with the text from `output["worked_faded"][0]`. Update `frontend/src/api.js` to match.
4. `GET /sessions/{id}` adds `analogy_bridging`, `reexplain`, `worked_faded`, `check_turns`, and `check_result`.
5. `dialogue()` only looks one level down, at a task named `socratic`. A paused check is two levels down, inside its method, so replace it with a recursive read that takes a key. `reviewer` and `check_turns` need the same read, because a paused subgraph's keys haven't reached the parent yet.

**Node names.** `events()` matches node names at any depth, and `wrap_up` reads `output["socratic"]`. New nodes must not be named `intake`, `planner`, `select_method`, `wrap_up`, or `teacher`. Only the moved quiz reuses `reviewer`.

**Frontend (`frontend/src/App.jsx`)**

1. Keep any check behind "Continue", the way `pendingQuestions` holds the quiz today, or the prompt appears before the user has read the lesson. "Continue" also swaps the lesson away, which is what makes `retrieval_practice` work without looking back.
2. `Quiz` sends all picks with `answerTutor` after the last question.
3. A reopened quiz only sends picks if `in_progress` is true. A finished session isn't waiting, so `/answer` would return 409.
4. Clear `inDialogue` on `done`. Today only `wrap_up` clears it, so the next message after a check would go to `/answer` and get a 409.
5. `openSession` hard-codes `saved.method === 'socratic'`. Rebuild each method from its own keys, and restore `inDialogue` for any paused text prompt.
6. Show `analogy`, `reexplain`, and the gaps from `check_result` as messages.
7. Sessions saved before this change have `reviewer` but no `check_result`, and must still open.

**CLI and docs**

1. The loop in `main.py` reads `value["question"]`, which raises a `KeyError` on a quiz. Print the questions and resume with a list of picks.
2. Update `CLAUDE.md` for the new flow, keys, and events.

## Shared state

State keys are named after the node or method that fills them. New Pydantic models go in `tutor/schemas.py`, because `db.serializer()` only allow-lists models defined there. Existing keys stay as they are.

| Key | Type | Set by | Purpose |
| --- | --- | --- | --- |
| `pick_check` | PickCheckResult | pick\_check | Which check runs and why |
| `check_result` | CheckResult | each check | Whether the user passed, and the gaps |
| `check_turns` | list of dialogue turns | text checks | Check prompts and answers, kept so sessions can reopen |
| `worked_faded` | list of dialogue turns | worked\_faded | The dialogue, kept so sessions can reopen |
| `analogy_bridging` | AnalogyLesson | analogy\_bridging | The lesson |
| `reexplain` | str | reexplain | The one re-explanation |

## File structure

New folders follow the same layout as the existing methods (`graph.py` with `build_graph()`, `nodes.py`). Prompts stay flat in `tutor/prompts/<name>.md`, loaded with `prompts.load(name)`, for example `worked_faded_next_problem.md` and `check_teach_back.md`.

```
tutor/
├── state.py                     # new keys above
├── schemas.py                   # new models, extended Literals
├── methods/
│   ├── __init__.py              # add worked_faded, analogy_bridging to METHODS
│   ├── structured_lesson/       # reviewer moves to checks/quiz/; add pick_check
│   ├── socratic/                # unchanged
│   ├── worked_faded/            # new
│   └── analogy_bridging/        # new, includes pick_check
├── checks/
│   ├── __init__.py              # CHECKS registry, add_checks()
│   ├── context.py               # taught_text()
│   ├── pick_check.py            # shared node
│   ├── quiz/                    # moved from structured_lesson
│   ├── retrieval_practice/
│   ├── teach_back/
│   └── erroneous_examples/
└── prompts/                     # new prompts; update select_method.md
```

**Testing.** Tests are handled by @jav, per `CLAUDE.md`. Structured lessons now pause, so `tests/test_api.py` (the expected event order) and `tests/test_graph.py` (the graph has no checkpointer) will need updating, and `FakeLLM` needs canned answers for the new schemas.

## Done when

- [ ] Lessons aren't duplicated after a check, in the saved session or on screen.
- [ ] Each check runs end to end from `structured_lesson` and `analogy_bridging`.
- [ ] A check reopens from the sidebar, both while paused and after finishing.
- [ ] One question makes one LLM call, including after resume.
- [ ] A failed `pick_check` falls back to `quiz`.
- [ ] Interrupt payloads don't include the planted mistake or other answers, except the quiz's existing `correct_answer`.
- [ ] A `worked_faded` run reaches a full problem, and the 6-problem limit ends with a direct walkthrough.
- [ ] Each example prompt in the rules table routes to the listed method.
- [ ] Sessions saved before this change still reopen.

## Out of scope

Do not build any of these, even if they seem like a natural next step:

- **Rules for picking a check.** `pick_check` is one LLM call that chooses what it thinks is most effective. No scoring, heuristics, or per-topic rules; those will come later.
- **Shared checks in `socratic` or `worked_faded`.** Both keep their own built-in checks. Do not change `socratic` at all.
- **Measuring method or check effectiveness.** No scoring of methods, LLM-as-judge, learning-event tables, bandits, preference ratings, or stats.
- **Spaced repetition.** `retrieval_practice` is only an in-lesson check. No review queue, scheduling, or resurfacing old topics.
- **Switching methods mid-lesson.** A method that gets stuck finishes inside its own subgraph and does not route to another method.
- **Other methods.** No productive failure or other new teaching methods.
- **Framework or model changes.** Stay on LangGraph; methods and checks are subgraphs, not agent tools. Don't change models, providers, or settings for existing nodes.
- **Unrelated refactors.** Don't rename existing state keys or restructure code beyond moving `quiz` into `tutor/checks/`. UI work is limited to the "API, frontend, and CLI" section. No math rendering, new tools, or new dependencies unless a requirement needs them.
