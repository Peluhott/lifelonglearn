from tutor import llm, prompts
from tutor.schemas import IntakeResult
from tutor.state import TutorState


INTAKE_INSTRUCTIONS = prompts.load("intake")


def intake_node(state: TutorState) -> dict:
    result = llm.structured(
        system=INTAKE_INSTRUCTIONS,
        content=state["user_prompt"],
        schema=IntakeResult,
    )
    return {"intake": result}