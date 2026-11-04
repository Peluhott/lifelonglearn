from langgraph.types import Send

from tutor import llm, prompts
from tutor.schemas import ReviewerResult, TaughtStep, TeacherResult
from tutor.state import TeacherTask, TutorState
from tutor.tools.images import generate_image

TEACHER_INSTRUCTIONS = prompts.load("teacher")
REVIEWER_INSTRUCTIONS = prompts.load("reviewer")


def teach_every_step(state: TutorState):
    """Start one teacher per plan step, all at once; with no steps, go straight to the reviewer."""
    plan = state["planner"]
    if not plan.steps:
        return "reviewer"
    # each Send runs the teacher with its own small input instead of the shared state
    return [Send("teacher", {"planner": plan, "step_index": i}) for i in range(len(plan.steps))]


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


def reviewer_node(state: TutorState) -> dict:
    taught = sorted(state.get("teacher", []), key=lambda t: t.index)  # parallel teachers finish in any order
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


def finish_node(state: TutorState) -> dict:
    return {"outcome": "completed"}
