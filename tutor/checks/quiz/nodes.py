from langgraph.types import Send

from tutor import llm, prompts
from tutor.checks.context import check_finished, taught_steps, taught_text
from tutor.schemas import ReviewerResult
from tutor.state import TutorState

REVIEWER_INSTRUCTIONS = prompts.load("reviewer")

MAX_RETEACHES = 2  # per step; after that a missed step ends as "still needs work"


def reviewer_node(state: TutorState) -> dict:
    if not taught_steps(state):
        return {}                            # nothing was taught, so there's nothing to review
    plan = state["planner"]
    result = llm.structured(
        system=REVIEWER_INSTRUCTIONS,
        content=f"Concept: {plan.concept_to_teach}\nMethod: {plan.method}\n\n{taught_text(state)}",
        schema=ReviewerResult,
    )
    return {"reviewer": result}  # one call covers every step


def reteach_missed(state: TutorState):
    """After a graded round, reteach every missed step that still has retries left (in parallel); otherwise finish."""
    rounds = state.get("grader", [])
    if not rounds:
        return "check_result"
    latest = rounds[-1]
    taught = {t.index: t for t in taught_steps(state)}
    retaught = state.get("reteacher", [])
    sends = []
    for graded in latest.answers:
        earlier = [r for r in retaught if r.index == graded.index]
        if not graded.is_correct and len(earlier) < MAX_RETEACHES:
            task = {"planner": state["planner"], "step": taught[graded.index], "graded": graded, "earlier": earlier, "round": latest.round}
            sends.append(Send("reteacher", task))
    return sends or "check_result"


def check_result_node(state: TutorState) -> dict:
    latest = {}  # a step's newest answer decides it, so a miss that was reteached and fixed isn't a gap
    for graded_round in state.get("grader", []):
        latest.update({a.index: a for a in graded_round.answers})
    return check_finished("quiz", [a.step for _, a in sorted(latest.items()) if not a.is_correct])
