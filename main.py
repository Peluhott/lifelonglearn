import uuid

from langgraph.types import Command

from tutor.graph import graph

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


config = {"configurable": {"thread_id": str(uuid.uuid4())}}
prompt = input("What are you stuck on?\n> ")
state = graph.invoke({"user_prompt": prompt}, config=config)
print(state["intake"].model_dump_json(indent=2))
print(state["planner"].model_dump_json(indent=2))
for result in sorted(state.get("teacher", []), key=lambda t: t.index):  # teachers run in parallel, so restore plan order
    print(result.model_dump_json(indent=2))
print("All steps covered")

# the grader pauses the graph for answers; keep answering until it finishes
while (snapshot := graph.get_state(config)).interrupts:
    picks = ask_quiz(snapshot.interrupts[0].value)
    state = graph.invoke(Command(resume=picks), config=config)
    graded = state["grader"][-1]
    print(f"\nScore: {sum(a.is_correct for a in graded.answers)} of {len(graded.answers)}")
    for retaught in sorted((r for r in state.get("reteacher", []) if r.round == graded.round), key=lambda r: r.index):
        print(f"\nLet's look at '{retaught.step}' again.\n{retaught.misconception}\n{retaught.explanation}")

missed = {a.index: a.step for g in state.get("grader", []) for a in g.answers if not a.is_correct}
fixed = {a.index for g in state.get("grader", []) for a in g.answers if a.is_correct}
still = [step for index, step in missed.items() if index not in fixed]
print("\nStill needs work: " + ", ".join(still) if still else "\nEvery step checked out.")
