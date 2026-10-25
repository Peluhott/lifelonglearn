from tutor import llm
from tutor.schemas import IntakeResult
from tutor.state import TutorState


INTAKE_INSTRUCTIONS = """You are the intake step of a tutoring system.
Your only job is to understand what the student brought and describe it accurately.
Do NOT teach, solve the problem, or guess at prerequisites - another agent does that.
Only fill fields with information that is actually in the student's message.
Leave a field empty rather than inventing details."""


def intake_node(state: TutorState) -> dict:
    result = llm.structured(
        system=INTAKE_INSTRUCTIONS,
        content=state["user_prompt"],
        schema=IntakeResult,
    )
    return {"intake": result}