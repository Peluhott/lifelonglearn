from tutor import llm, prompts
from tutor.schemas import TaughtStep, TeacherResult
from tutor.state import TutorState
from tutor.tools.images import generate_image

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

    image = None
    if result.image_prompt:              # the teacher only asks for a picture when it really helps
        try:
            image = generate_image(result.image_prompt)
        except Exception as e:           # a failed image shouldn't stop the lesson
            print(f"Image generation failed for step {index + 1}: {e}")

    taught = TaughtStep(**result.model_dump(), image=image)
    return {"teacher": [taught], "planner_index": index + 1}  # list so it gets appended, then move to the next step
