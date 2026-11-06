from tutor import llm, prompts
from tutor.checks.context import check_context
from tutor.schemas import PickCheckResult
from tutor.state import TutorState

PICK_CHECK_INSTRUCTIONS = prompts.load("pick_check")


def pick_check_node(state: TutorState) -> dict:
    try:
        result = llm.structured(system=PICK_CHECK_INSTRUCTIONS, content=check_context(state), schema=PickCheckResult)
    except Exception as e:  # choosing a check shouldn't stop the lesson
        print(f"Check selection failed: {e}")
        result = PickCheckResult(check="quiz", reason="Selection failed, so the default check was used.")
    return {"pick_check": result}


def route_to_check(state: TutorState) -> str:
    return state["pick_check"].check
