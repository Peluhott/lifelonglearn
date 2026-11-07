from tutor import llm, prompts
from tutor.schemas import AnalogyLesson, ReexplainResult
from tutor.state import TutorState

ANALOGY_INSTRUCTIONS = prompts.load("analogy_bridging")
REEXPLAIN_INSTRUCTIONS = prompts.load("reexplain")


def analogy_lesson_node(state: TutorState) -> dict:
    result = llm.structured(
        system=ANALOGY_INSTRUCTIONS,
        content=f"Student's request: {state['user_prompt']}\nConcept: {state['planner'].concept_to_teach}",
        schema=AnalogyLesson,
    )
    return {"analogy_bridging": result}


def after_check(state: TutorState) -> str:
    return "reexplain" if state["check_result"].gaps else "finish"


def reexplain_node(state: TutorState) -> dict:
    result = llm.structured(
        system=REEXPLAIN_INSTRUCTIONS,
        content=(
            f"Concept: {state['planner'].concept_to_teach}\n"
            f"The lesson: {state['analogy_bridging'].model_dump_json()}\n"
            f"What the student missed: {state['check_result'].gaps}"
        ),
        schema=ReexplainResult,
    )
    return {"reexplain": result.text}


def finish_node(state: TutorState) -> dict:
    check = state.get("check_result")  # missing when the student skipped the test
    return {"outcome": "stuck" if check and not check.passed else "completed"}
