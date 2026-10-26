from tutor import llm
from tutor.schemas import ReviewerResult
from tutor.state import TutorState

REVIEWER_INSTRUCTIONS = """ You are the reviewer step of a tutoring system, reviewer in this system means
that you're checking for understanding of the student with what was just taught. i'm going to give you the concept,
the method, and every step that was taught along with the explanation the student was given for it.
for each step write one multiple choice question based on that explanation, give 4 choices where one is correct
and 3 are plausible wrong answers, and mark which one is correct. only write the questions, dont grade anything
or ask the student for answers, that happens later. dont use any code or math in the questions for now"""

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
