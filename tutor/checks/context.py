from langgraph.types import interrupt

from tutor.schemas import CheckResult, DialogueTurn, TaughtStep
from tutor.state import CheckState, TutorState


def taught_steps(state: TutorState) -> list[TaughtStep]:
    """What was just taught, in order. An analogy lesson has no teacher steps, so its three parts stand in for them."""
    lesson = state.get("analogy_bridging")
    if lesson:
        parts = [
            ("The explanation", lesson.explanation),
            ("The mapping", "\n".join(lesson.mapping)),
            ("Where the analogy breaks down", lesson.limits),
        ]
        return [TaughtStep(step=step, explanation=text, index=i) for i, (step, text) in enumerate(parts)]
    return sorted(state.get("teacher", []), key=lambda t: t.index)  # parallel teachers finish in any order


def taught_text(state: TutorState) -> str:
    return "\n\n".join(f"Step: {t.step}\nExplanation: {t.explanation}" for t in taught_steps(state))


def check_context(state: TutorState) -> str:
    return f"Concept: {state['planner'].concept_to_teach}\n\nWhat was taught:\n{taught_text(state)}"


def wait_for_answer_node(state: CheckState) -> dict:
    # kept apart from the LLM nodes because this node reruns from the top on resume
    answer = interrupt({"question": state["check_turns"][-1].text})
    return {"last_answer": answer, "check_turns": [DialogueTurn(role="student", text=answer)]}


def check_finished(check_type: str, gaps: list[str]) -> dict:
    return {"check_result": CheckResult(check_type=check_type, passed=not gaps, gaps=gaps)}
