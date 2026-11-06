from langgraph.types import interrupt

from tutor import llm, prompts
from tutor.schemas import DialogueTurn, FadedProblem, FadedWrapUp, StepEvaluation
from tutor.state import TutorState

MAX_PROBLEMS = 6      # the worked example counts as problem 1
MAX_MISSES = 2        # this many in a row goes back one level

NEXT_PROBLEM_INSTRUCTIONS = prompts.load("worked_faded_next_problem")
EVALUATE_STEP_INSTRUCTIONS = prompts.load("worked_faded_evaluate_step")
WHY_FEEDBACK_INSTRUCTIONS = prompts.load("worked_faded_why_feedback")
WRAP_UP_INSTRUCTIONS = prompts.load("worked_faded_wrap_up")


class WorkedFadedState(TutorState, total=False):
    """TutorState plus keys that stay inside this subgraph."""

    problem: FadedProblem
    first_problem: FadedProblem   # every variant keeps its step structure
    used_problems: list[str]
    level: int                    # how many steps, from the end, the student completes
    problems_seen: int
    step_index: int               # the step being asked
    misses: int                   # problems missed in a row
    last_answer: str
    carry: str                    # feedback that opens the next tutor turn
    new_problem: bool
    problem_over: bool
    solved_full: bool


def solved_lines(problem: FadedProblem, count: int, with_why: bool = False) -> str:
    lines = []
    for i, step in enumerate(problem.steps[:count]):
        lines.append(f"Step {i + 1}: {step.work}" + (f"\n  Why: {step.why}" if with_why else ""))
    return "\n".join(lines)


def next_problem_node(state: WorkedFadedState) -> dict:
    first = state.get("first_problem")
    used = state.get("used_problems", [])
    content = f"Student's request: {state['user_prompt']}\nConcept: {state['planner'].concept_to_teach}"
    if first:
        content += f"\n\nKeep exactly this step structure: {first.model_dump_json()}\nDon't reuse these problems: {used}"
    problem = llm.structured(system=NEXT_PROBLEM_INSTRUCTIONS, content=content, schema=FadedProblem)
    level = state.get("level", 1)
    return {
        "problem": problem,
        "first_problem": first or problem,
        "used_problems": [*used, problem.problem],
        "level": level,
        "misses": state.get("misses", 0),
        "problems_seen": state.get("problems_seen", 0) + 1,
        "step_index": max(len(problem.steps) - level, 0),  # remove steps from the end first
        "new_problem": True,
        "problem_over": False,
        "solved_full": False,
    }


def ask_step_node(state: WorkedFadedState) -> dict:
    problem, index = state["problem"], state["step_index"]
    parts = [state["carry"]] if state.get("carry") else []
    if state["problems_seen"] == 1:
        parts += [f"Here's a worked example.\n\n{problem.problem}", solved_lines(problem, len(problem.steps), True), problem.why_question]
    else:
        if state["new_problem"]:
            parts.append(f"New problem: {problem.problem}")
            if index:
                parts.append(solved_lines(problem, index))
            else:
                parts.append("This one is all yours, one step at a time.")
        parts.append(f"Step {index + 1}: {problem.steps[index].task}")
    return {"worked_faded": [DialogueTurn(role="tutor", text="\n\n".join(parts))], "carry": "", "new_problem": False}


def wait_for_step_node(state: WorkedFadedState) -> dict:
    # kept apart from the LLM nodes because this node reruns from the top on resume
    answer = interrupt({"question": state["worked_faded"][-1].text})
    return {"last_answer": answer, "worked_faded": [DialogueTurn(role="student", text=answer)]}


def evaluate_step_node(state: WorkedFadedState) -> dict:
    problem, index = state["problem"], state["step_index"]
    if state["problems_seen"] == 1:  # the worked example's "why" answer gets feedback and doesn't change the level
        result = llm.structured(
            system=WHY_FEEDBACK_INSTRUCTIONS,
            content=f"Solution: {problem.model_dump_json()}\nStudent's answer: {state['last_answer']}",
            schema=StepEvaluation,
        )
        return {"carry": result.feedback, "problem_over": True}

    step = problem.steps[index]
    result = llm.structured(
        system=EVALUATE_STEP_INSTRUCTIONS,
        content=(
            f"Problem: {problem.problem}\nSolved so far: {solved_lines(problem, index)}\n"
            f"This step: {step.task}\nExpected: {step.work}\nStudent's answer: {state['last_answer']}"
        ),
        schema=StepEvaluation,
    )
    if not result.correct:
        misses = state["misses"] + 1
        level = state["level"]
        if misses >= MAX_MISSES:
            level, misses = max(level - 1, 1), 0
        return {
            "carry": f"{result.feedback}\nThe correct step was: {step.work}",
            "misses": misses,
            "level": level,
            "problem_over": True,
        }
    if index + 1 < len(problem.steps):
        return {"carry": result.feedback, "step_index": index + 1}
    return {
        "carry": result.feedback,
        "misses": 0,
        "level": state["level"] + 1,
        "problem_over": True,
        "solved_full": state["level"] >= len(problem.steps),
    }


def after_step(state: WorkedFadedState) -> str:
    if state["solved_full"]:
        return "faded_wrap_up"
    if not state["problem_over"]:
        return "ask_step"
    return "faded_wrap_up" if state["problems_seen"] >= MAX_PROBLEMS else "next_problem"


def faded_wrap_up_node(state: WorkedFadedState) -> dict:
    solved = state["solved_full"]
    result = llm.structured(
        system=WRAP_UP_INSTRUCTIONS,
        content=(
            f"Concept: {state['planner'].concept_to_teach}\n"
            f"The student solved a full problem alone: {'yes' if solved else 'no'}\n"
            f"The last problem: {state['problem'].model_dump_json()}"
        ),
        schema=FadedWrapUp,
    )
    text = f"{state['carry']}\n\n{result.text}" if state.get("carry") else result.text
    return {"worked_faded": [DialogueTurn(role="tutor", text=text)], "outcome": "completed" if solved else "stuck"}
