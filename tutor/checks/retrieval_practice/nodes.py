from tutor import llm, prompts
from tutor.checks.context import check_context, check_finished
from tutor.schemas import DialogueTurn, GapEvaluation
from tutor.state import CheckState

RETRIEVAL_INSTRUCTIONS = prompts.load("check_retrieval_practice")


def ask_recall_node(state: CheckState) -> dict:
    concept = state["planner"].concept_to_teach
    text = f"Without looking back, write down the key points you remember about {concept}."
    return {"check_turns": [DialogueTurn(role="tutor", text=text)]}


def check_result_node(state: CheckState) -> dict:
    result = llm.structured(
        system=RETRIEVAL_INSTRUCTIONS,
        content=f"{check_context(state)}\n\nWhat the student wrote from memory:\n{state['last_answer']}",
        schema=GapEvaluation,
    )
    return check_finished("retrieval_practice", result.gaps)
