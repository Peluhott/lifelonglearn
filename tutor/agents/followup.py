from tutor import llm, prompts
from tutor.schemas import FollowUp, FollowUpResult, PlannerResult, TaughtStep

FOLLOWUP_INSTRUCTIONS = prompts.load("followup")


def answer_followup(plan: PlannerResult, step: TaughtStep, earlier: list[FollowUp], question: str) -> FollowUpResult:
    """Answer a question about one taught step. Called by the API after the graph has finished, so it isn't a graph node."""
    history = "\n\n".join(f"Student asked: {f.question}\nYou answered: {f.answer}" for f in earlier)
    content = (
        f"Concept: {plan.concept_to_teach}\nMethod: {plan.method}\n\n"
        f"Step: {step.step}\nExplanation: {step.explanation}\n\n"
        + (f"Earlier questions about this step:\n{history}\n\n" if history else "")
        + f"New question: {question}"
    )
    return llm.structured(system=FOLLOWUP_INSTRUCTIONS, content=content, schema=FollowUpResult)
