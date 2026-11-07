from statistics import mean

from tutor import llm, prompts
from tutor.checks.context import check_context
from tutor.schemas import ErrorRubric, FadedRubric, RecallRubric, SocraticRubric

RUBRIC_VERSION = 1
LEVELS = {"none": 0.0, "weak": 1 / 3, "good": 2 / 3, "full": 1.0}
DIALOGUES = ("socratic", "worked_faded")

RECALL_INSTRUCTIONS = prompts.load("judge_recall")

# test type -> the instructions and form its judge fills in
RUBRICS = {
    "socratic": (prompts.load("judge_socratic"), SocraticRubric),
    "worked_faded": (prompts.load("judge_worked_faded"), FadedRubric),
    "teach_back": (RECALL_INSTRUCTIONS, RecallRubric),
    "retrieval_practice": (RECALL_INSTRUCTIONS, RecallRubric),
    "erroneous_examples": (prompts.load("judge_erroneous_examples"), ErrorRubric),
}


def testing_method(values: dict) -> str | None:
    """How a finished session tested the student: a check, a dialogue that tests as it teaches, or nothing."""
    check = values.get("pick_check")
    if check:
        return check.check
    method = values["select_method"].chosen_method
    return method if method in DIALOGUES else None


def judged_content(method: str, values: dict) -> str:
    if method in DIALOGUES:
        turns = values.get(method, [])
        context = f"Student's request: {values['user_prompt']}\nConcept: {values['planner'].concept_to_teach}"
    else:
        turns = values.get("check_turns", [])
        context = f"{check_context(values)}\n\nGaps the check found: {values['check_result'].gaps}"
    dialogue = "\n".join(f"{turn.role}: {turn.text}" for turn in turns)
    return f"{context}\n\nThe whole exchange:\n{dialogue}"


def score_session(method: str | None, values: dict) -> dict | None:
    """The score for a finished session, or None if nothing tested the student.

    Called by the API after the graph has finished, so it isn't a graph node. A quiz is scored on its first try, because
    later rounds come after reteaching. Everything else gets one judge call, and the score is worked out here so the
    model never writes the number itself.
    """
    if method is None:
        return None
    if method == "quiz":
        rounds = values.get("grader", [])
        if not rounds:
            return None
        answers = rounds[0].answers
        return {"score": sum(a.is_correct for a in answers) / len(answers)}

    instructions, rubric = RUBRICS[method]
    result = llm.structured(system=instructions, content=judged_content(method, values), schema=rubric)
    ratings = result.model_dump()
    return {
        "score": mean(LEVELS[rating["level"]] for rating in ratings.values()),
        "detail": ratings,
        "rubric_version": RUBRIC_VERSION,
        "judge_model": llm.MODEL,
    }
