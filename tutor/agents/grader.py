from langgraph.types import interrupt

from tutor.schemas import GradedAnswer, GraderResult, QuizQuestion
from tutor.state import TutorState


def is_correct(picked: str, correct_answer: str) -> bool:
    # strip so a stray space from the model doesn't make the right answer look wrong
    return picked.strip() == correct_answer.strip()


def current_questions(state: TutorState) -> list[QuizQuestion]:
    """Round 1 is the reviewer's quiz; each later round asks the new questions from the previous round's reteaches."""
    rounds_done = len(state.get("grader", []))
    if rounds_done == 0:
        reviewer = state.get("reviewer")
        if not reviewer:
            return []
        # the reviewer writes one question per taught step, in step order
        taught = sorted(state.get("teacher", []), key=lambda t: t.index)
        return [QuizQuestion(**q.model_dump(), index=t.index) for t, q in zip(taught, reviewer.questions)]
    retaught = sorted((r for r in state.get("reteacher", []) if r.round == rounds_done), key=lambda r: r.index)
    return [QuizQuestion(**r.question.model_dump(), index=r.index) for r in retaught]


def quiz_payload(round: int, questions: list[QuizQuestion]) -> dict:
    """What the student is shown: the questions without their answers."""
    return {"round": round, "questions": [q.model_dump(exclude={"correct_answer"}) for q in questions]}


def grader_node(state: TutorState) -> dict:
    questions = current_questions(state)
    if not questions:
        return {}
    round = len(state.get("grader", [])) + 1
    # pauses the graph until the API resumes it with Command(resume=[one pick per question]).
    # On resume this node runs again from the top, so nothing above this line may have side effects.
    picks = interrupt(quiz_payload(round, questions))
    answers = [
        GradedAnswer(
            index=q.index,
            step=q.step,
            question=q.question,
            choices=q.choices,
            picked=picked,
            correct_answer=q.correct_answer,
            is_correct=is_correct(picked, q.correct_answer),
        )
        for q, picked in zip(questions, picks)
    ]
    return {"grader": [GraderResult(round=round, answers=answers)]}
