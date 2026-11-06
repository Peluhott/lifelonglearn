from tutor import llm, prompts
from tutor.checks.context import check_context, check_finished
from tutor.schemas import DialogueTurn, GapEvaluation, TeachBackTurn
from tutor.state import CheckState

MAX_FOLLOW_UPS = 3

FOLLOW_UP_INSTRUCTIONS = prompts.load("check_teach_back_follow_up")
EVALUATE_INSTRUCTIONS = prompts.load("check_teach_back")


class TeachBackState(CheckState, total=False):
    follow_ups: int


def exchange(state: TeachBackState) -> str:
    return "\n".join(f"{turn.role}: {turn.text}" for turn in state["check_turns"])


def ask_to_explain_node(state: TeachBackState) -> dict:
    concept = state["planner"].concept_to_teach
    text = f"I'm a student who's lost on {concept}. Can you explain it to me in your own words?"
    return {"check_turns": [DialogueTurn(role="tutor", text=text)], "follow_ups": 0}


def follow_up_node(state: TeachBackState) -> dict:
    result = llm.structured(
        system=FOLLOW_UP_INSTRUCTIONS,
        content=f"{check_context(state)}\n\nThe conversation so far:\n{exchange(state)}",
        schema=TeachBackTurn,
    )
    if not result.follow_up:
        return {"follow_ups": MAX_FOLLOW_UPS + 1}  # the model stopped asking
    return {
        "check_turns": [DialogueTurn(role="tutor", text=result.follow_up)],
        "follow_ups": state["follow_ups"] + 1,
    }


def after_follow_up(state: TeachBackState) -> str:
    return "check_result" if state["follow_ups"] > MAX_FOLLOW_UPS else "wait_for_answer"


def after_answer(state: TeachBackState) -> str:
    return "check_result" if state["follow_ups"] >= MAX_FOLLOW_UPS else "follow_up"


def check_result_node(state: TeachBackState) -> dict:
    result = llm.structured(
        system=EVALUATE_INSTRUCTIONS,
        content=f"{check_context(state)}\n\nThe whole exchange:\n{exchange(state)}",
        schema=GapEvaluation,
    )
    return check_finished("teach_back", result.gaps)
