from tutor import llm, prompts
from tutor.schemas import PlannerResult
from tutor.state import TutorState

PLANNER_INSTRUCTIONS = prompts.load("planner")

def planner_node(state: TutorState) -> dict:
    result = llm.structured(
        system=PLANNER_INSTRUCTIONS,
        content=state["intake"].model_dump_json(),
        schema=PlannerResult,
    )
    return {"planner": result}
