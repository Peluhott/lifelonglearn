from tutor import llm, prompts
from tutor.schemas import ReviewerResult
from tutor.state import TutorState

REVIEWER_INSTRUCTIONS = prompts.load("reviewer")

def reviewer_node(state: TutorState) -> dict:
    taught = state.get("teacher", [])
    if not taught:
        return {}                            # nothing was taught, so there's nothing to review
    plan = state["planner"]
    lessons = "\n\n".join(f"Step: {t.step}\nExplanation: {t.explanation}" for t in taught)
    result = llm.structured(
        system=REVIEWER_INSTRUCTIONS,
        content=f"Concept: {plan.concept_to_teach}\nMethod: {plan.method}\n\n{lessons}",
        schema=ReviewerResult,
    )
    return {"reviewer": result}  # one call covers every step
