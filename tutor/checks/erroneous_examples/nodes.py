from tutor import llm, prompts
from tutor.checks.context import check_context, check_finished
from tutor.schemas import DialogueTurn, ErroneousExample, GapEvaluation
from tutor.state import CheckState

PLANT_INSTRUCTIONS = prompts.load("check_erroneous_plant")
EVALUATE_INSTRUCTIONS = prompts.load("check_erroneous_examples")


class ErroneousState(CheckState, total=False):
    planted_mistake: str   # stays here; never in an interrupt payload


def plant_mistake_node(state: ErroneousState) -> dict:
    result = llm.structured(system=PLANT_INSTRUCTIONS, content=check_context(state), schema=ErroneousExample)
    text = f"This has one mistake in it. Find it and fix it.\n\n{result.example}"
    return {"check_turns": [DialogueTurn(role="tutor", text=text)], "planted_mistake": result.mistake}


def check_result_node(state: ErroneousState) -> dict:
    result = llm.structured(
        system=EVALUATE_INSTRUCTIONS,
        content=(
            f"The example: {state['check_turns'][0].text}\n\n"
            f"The planted mistake: {state['planted_mistake']}\n\n"
            f"What the student said: {state['last_answer']}"
        ),
        schema=GapEvaluation,
    )
    return check_finished("erroneous_examples", result.gaps)
