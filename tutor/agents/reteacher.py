from tutor import llm, prompts
from tutor.schemas import ReteachResult, RetaughtStep
from tutor.state import ReteachTask

RETEACHER_INSTRUCTIONS = prompts.load("reteacher")


def reteacher_node(task: ReteachTask) -> dict:
    plan, step, graded = task["planner"], task["step"], task["graded"]
    earlier = "".join(
        f"\n\nAn earlier re-explanation that still didn't land:\n{r.explanation}" for r in task["earlier"]
    )
    result = llm.structured(
        system=RETEACHER_INSTRUCTIONS,
        content=(
            f"Concept: {plan.concept_to_teach}\nMethod: {plan.method}\n\n"
            f"Step: {step.step}\nOriginal explanation: {step.explanation}{earlier}\n\n"
            f"Question they missed: {graded.question}\nChoices: {' | '.join(graded.choices)}\n"
            f"Student picked: {graded.picked}\nCorrect answer: {graded.correct_answer}"
        ),
        schema=ReteachResult,
    )
    retaught = RetaughtStep(**result.model_dump(), step=step.step, index=step.index, round=task["round"])
    return {"reteacher": [retaught]}  # a list so parallel reteachers' results are appended
