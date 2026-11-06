import uuid

from langgraph.types import Command

from tutor.graph import graph, live_snapshot, method_values

LETTERS = "ABCD"


def ask_quiz(quiz: dict) -> list[str]:
    """Show one quiz round in the terminal and return the picked choice for each question."""
    print(f"\n--- Quiz, round {quiz['round']} ---")
    picks = []
    for q in quiz["questions"]:
        print(f"\n{q['question']}")
        for letter, choice in zip(LETTERS, q["choices"]):
            print(f"  {letter}) {choice}")
        letter = ""
        while letter not in LETTERS[: len(q["choices"])] or not letter:
            letter = input("> ").strip().upper()[:1]
        picks.append(q["choices"][LETTERS.index(letter)])
    return picks


def current() -> tuple:
    snapshot = graph.get_state(config, subgraphs=True)
    return live_snapshot(snapshot), method_values(snapshot)


config = {"configurable": {"thread_id": str(uuid.uuid4())}}
prompt = input("What are you stuck on?\n> ")
graph.invoke({"user_prompt": prompt}, config=config)

snapshot, state = current()
print(state["intake"].model_dump_json(indent=2))
print(state["planner"].model_dump_json(indent=2))
print(state["select_method"].model_dump_json(indent=2))
for result in sorted(state.get("teacher", []), key=lambda t: t.index):  # teachers run in parallel, so restore plan order
    print(result.model_dump_json(indent=2))

# both methods pause the graph for the student: a quiz wants picks, a Socratic question wants a typed answer
while snapshot.interrupts:
    pause = snapshot.interrupts[0].value
    is_quiz = "questions" in pause
    answer = ask_quiz(pause) if is_quiz else input(f"{pause['question']}\n> ")
    graph.invoke(Command(resume=answer), config=config)
    snapshot, state = current()
    if is_quiz:
        graded = state["grader"][-1]
        print(f"\nScore: {sum(a.is_correct for a in graded.answers)} of {len(graded.answers)}")
        for retaught in sorted((r for r in state.get("reteacher", []) if r.round == graded.round), key=lambda r: r.index):
            print(f"\nLet's look at '{retaught.step}' again.\n{retaught.misconception}\n{retaught.explanation}")

if state.get("socratic"):
    print(state["socratic"][-1].text)  # the wrap-up
if state.get("grader"):
    missed = {a.index: a.step for g in state["grader"] for a in g.answers if not a.is_correct}
    fixed = {a.index for g in state["grader"] for a in g.answers if a.is_correct}
    still = [step for index, step in missed.items() if index not in fixed]
    print("\nStill needs work: " + ", ".join(still) if still else "\nEvery step checked out.")
print(f"Finished: {state['outcome']}")
