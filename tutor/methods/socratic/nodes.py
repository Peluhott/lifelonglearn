from langgraph.types import interrupt

from tutor import llm, prompts
from tutor.schemas import AnswerEvaluation, DialogueTurn, SocraticQuestion, SocraticTarget, SocraticWrapUp
from tutor.state import TutorState

MAX_TURNS = 99  # placeholder until the real limit is decided
MAX_MISSES = 2  # a partial or misconception this many times in a row gets a hint

SET_TARGET_INSTRUCTIONS = prompts.load("socratic_set_target")
ASK_QUESTION_INSTRUCTIONS = prompts.load("socratic_ask_question")
EVALUATE_ANSWER_INSTRUCTIONS = prompts.load("socratic_evaluate_answer")
GIVE_HINT_INSTRUCTIONS = prompts.load("socratic_give_hint")
WRAP_UP_INSTRUCTIONS = prompts.load("socratic_wrap_up")


class SocraticState(TutorState, total=False):
    """TutorState plus keys that stay inside this subgraph."""

    target_insight: str
    premises: list[str]
    misconceptions: list[str]
    turns: int                    # questions and hints asked so far
    misses: int                   # partial or misconception answers in a row
    last_answer: str
    evaluation: AnswerEvaluation


def lesson_context(state: SocraticState) -> str:
    dialogue = "\n".join(f"{turn.role}: {turn.text}" for turn in state.get("socratic", []))
    evaluation = state.get("evaluation")
    verdict = evaluation.verdict if evaluation else "none yet"
    return (
        f"Student's request: {state['user_prompt']}\n"
        f"Concept: {state['planner'].concept_to_teach}\n"
        f"Target insight: {state['target_insight']}\n"
        f"Premises: {state['premises']}\n"
        f"Misconceptions to watch for: {state['misconceptions']}\n"
        f"Verdict on the last answer: {verdict}\n\n"
        f"Dialogue so far:\n{dialogue or '(nothing yet)'}"
    )


def set_target_node(state: SocraticState) -> dict:
    result = llm.structured(
        system=SET_TARGET_INSTRUCTIONS,
        content=f"Student's request: {state['user_prompt']}\nConcept: {state['planner'].concept_to_teach}",
        schema=SocraticTarget,
    )
    return {**result.model_dump(), "turns": 0, "misses": 0}


def ask_question_node(state: SocraticState) -> dict:
    result = llm.structured(
        system=ASK_QUESTION_INSTRUCTIONS,
        content=lesson_context(state),
        schema=SocraticQuestion,
    )
    return {"socratic": [DialogueTurn(role="tutor", text=result.question)], "turns": state["turns"] + 1}


def wait_for_answer_node(state: SocraticState) -> dict:
    # kept apart from the LLM nodes because this node reruns from the top on resume
    answer = interrupt({"question": state["socratic"][-1].text})
    return {"last_answer": answer, "socratic": [DialogueTurn(role="student", text=answer)]}


def evaluate_answer_node(state: SocraticState) -> dict:
    result = llm.structured(
        system=EVALUATE_ANSWER_INSTRUCTIONS,
        content=f"{lesson_context(state)}\n\nAnswer to evaluate: {state['last_answer']}",
        schema=AnswerEvaluation,
    )
    missed = result.verdict in ("partial", "misconception")
    return {"evaluation": result, "misses": state["misses"] + 1 if missed else 0}


def after_evaluation(state: SocraticState) -> str:
    evaluation = state["evaluation"]
    if evaluation.reached_target or state["turns"] >= MAX_TURNS:
        return "wrap_up"
    if evaluation.verdict == "stuck" or state["misses"] >= MAX_MISSES:
        return "give_hint"
    return "ask_question"


def give_hint_node(state: SocraticState) -> dict:
    result = llm.structured(
        system=GIVE_HINT_INSTRUCTIONS,
        content=lesson_context(state),
        schema=SocraticQuestion,
    )
    return {
        "socratic": [DialogueTurn(role="tutor", text=result.question)],
        "turns": state["turns"] + 1,
        "misses": 0,
    }


def wrap_up_node(state: SocraticState) -> dict:
    reached = state["evaluation"].reached_target
    result = llm.structured(
        system=WRAP_UP_INSTRUCTIONS,
        content=f"{lesson_context(state)}\n\nThe student reached the target insight: {'yes' if reached else 'no'}",
        schema=SocraticWrapUp,
    )
    text = result.explanation
    if result.terms:
        text += "\n\nTerms:\n" + "\n".join(f"- {term}" for term in result.terms)
    return {
        "socratic": [DialogueTurn(role="tutor", text=text)],
        "outcome": "completed" if reached else "stuck",
    }
