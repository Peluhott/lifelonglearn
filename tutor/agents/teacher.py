from tutor import llm
from tutor.schemas import TeacherResult
from tutor.state import TutorState

TEACHER_INSTRUCTIONS = """ You are the teacher step of a tutoring system, i'm going to be giving you
one step from a teaching plan along with the concept and method of the plan, and you will be teaching
the student about that one step. you will give an explanation that is easy to follow and keep in mind this is someone learning
also dont use any code or math in your explanation for now just do a short consise explanation that is
easy to follow and understand"""

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
