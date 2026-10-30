from tutor import llm, prompts
from tutor.schemas import TeacherResult
from tutor.state import TutorState

TEACHER_INSTRUCTIONS = prompts.load("teacher")

def teacher_node(state: TutorState) -> dict:
    plan = state["planner"]
    index = state["planner_index"]
    step = plan.steps[index]             # the one step we're teaching this time
    result = llm.structured(
        system=TEACHER_INSTRUCTIONS,
        content=f"Concept: {plan.concept_to_teach}\nMethod: {plan.method}\nStep to teach: {step}",
        schema=TeacherResult,
    )
    return {"teacher": [result], "planner_index": index + 1}  # list so it gets appended, then move to the next step
