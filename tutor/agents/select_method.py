from tutor import llm, prompts
from tutor.schemas import SelectMethodResult
from tutor.state import TutorState

SELECT_METHOD_INSTRUCTIONS = prompts.load("select_method")


def select_method_node(state: TutorState) -> dict:
    try:
        result = llm.structured(
            system=SELECT_METHOD_INSTRUCTIONS,
            content=(
                f"Student's request: {state['user_prompt']}\n"
                f"Intake: {state['intake'].model_dump_json()}\n"
                f"Plan: {state['planner'].model_dump_json()}"
            ),
            schema=SelectMethodResult,
        )
    except Exception as e:  # choosing a method shouldn't stop the lesson
        print(f"Method selection failed: {e}")
        result = SelectMethodResult(
            chosen_method="structured_lesson",
            request_type="unclear",
            reason="Selection failed, so the default method was used.",
        )
    return {"select_method": result}
