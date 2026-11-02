from tutor import llm, prompts
from tutor.schemas import TaughtStep, TeacherResult
from tutor.state import TeacherTask
from tutor.tools.images import generate_image

TEACHER_INSTRUCTIONS = prompts.load("teacher")

def teacher_node(task: TeacherTask) -> dict:
    plan = task["planner"]
    index = task["step_index"]
    step = plan.steps[index]             # the one step this teacher is teaching
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

    taught = TaughtStep(**result.model_dump(), image=image, index=index)
    return {"teacher": [taught]}  # a list so it gets appended next to the other teachers' results
