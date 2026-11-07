import random

from tutor import history, llm, prompts
from tutor.schemas import SelectMethodResult
from tutor.state import TutorState

SELECT_METHOD_INSTRUCTIONS = prompts.load("select_method")


def why_picked(result: SelectMethodResult, hint: str, trying: list[str]) -> str:
    if result.student_asked:
        return "requested"
    if result.chosen_method in trying:
        return "exploring"
    return "history" if hint else "normal"


def select_method_node(state: TutorState) -> dict:
    rows = state.get("history", [])
    category = state["intake"].category
    scoped, _ = history.in_scope(rows, category)
    explore = bool(scoped) and random.random() < history.EXPLORE_RATE
    trying = history.least_tried(scoped) if explore else []
    hint = history.build_hint(rows, category, explore)
    content = (
        f"Student's request: {state['user_prompt']}\n"
        f"Intake: {state['intake'].model_dump_json()}\n"
        f"Plan: {state['planner'].model_dump_json()}"
    )
    if hint:
        content += f"\n\n{hint}"
    try:
        result = llm.structured(system=SELECT_METHOD_INSTRUCTIONS, content=content, schema=SelectMethodResult)
    except Exception as e:  # choosing a method shouldn't stop the lesson
        print(f"Method selection failed: {e}")
        result = SelectMethodResult(
            chosen_method="structured_lesson",
            request_type="unclear",
            reason="Selection failed, so the default method was used.",
        )
        return {"select_method": result, "pick_reason": "normal"}
    return {"select_method": result, "pick_reason": why_picked(result, hint, trying)}
