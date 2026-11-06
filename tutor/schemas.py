"""
Data shapes passed between agents.

Each class is a Pydantic model that:
  - validates data when it's created (bad data -> ValidationError)
  - doubles as the answer format we send to the model
    (field names, allowed values, and descriptions become instructions)

No behavior lives here - only shapes.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Intake -> Planner
# ---------------------------------------------------------------------------
class IntakeResult(BaseModel):
    """What the intake agent understood about the student's request."""

    task_type: Literal[
        "stuck_on_problem",   # has a specific problem they can't solve
        "explain_concept",    # wants a concept explained
        "exam_prep",          # reviewing for a test
        "check_work",         # wants their answer/solution checked
        "unclear",            # can't tell yet
    ] = Field(description="What kind of help the student is asking for.")

    subject: Optional[str] = Field(
        None, description="Broad subject, e.g. 'Calculus I', 'Operating Systems'."
    )
    target_concept: Optional[str] = Field(
        None, description="The main concept they need help with, e.g. 'chain rule'."
    )
    mentioned_concepts: list[str] = Field(
        default_factory=list,
        description="Other concepts explicitly mentioned or clearly involved in the problem.",
    )
    source_problem: Optional[str] = Field(
        None, description="The exact problem or question they brought, if any, copied cleanly."
    )
    confusion_type: Literal["specific", "everything", "unstated"] = Field(
        description="'specific' if they named what confuses them, 'everything' if they "
        "said they don't get any of it, 'unstated' if they didn't say."
    )
    user_statement: Optional[str] = Field(
        None, description="What they said about their confusion, in their own words."
    )
    user_attempt: Optional[str] = Field(
        None, description="Any work or attempt they showed, copied as-is."
    )
    level_hint: Optional[str] = Field(
        None, description="Any hint about their level, e.g. 'high school', 'college intro course'."
    )
    deadline_hint: Optional[str] = Field(
        None, description="Any mention of timing, e.g. 'exam Friday'."
    )

# ---------------------------------------------------------------------------
# Intake -> Planner
# ---------------------------------------------------------------------------
class PlannerResult(BaseModel):
    """The teaching plan that the planner agent came up with to teach"""

    #I need to define the different parts
    # so I guess I would take the result from the intake agent and come up with a concept that I have to teach
    # then I'll split that concept into steps that I have to teach it in, how am i going to teach, and when should i be testting
    #for understanding

    concept_to_teach: str = Field(description="The main concept that the planner agent has decided to teach.")

    steps: list[str] = Field(
        default_factory=list,
        description="The steps that the planner agent has decided to teach the concept in."
    )

    method: str = Field(
        description="The main method that the planner agent has decided to use to teach the concept."
    )

# ---------------------------------------------------------------------------
# Planner -> Teacher   (round 2: Plan, Step)
# Teacher -> Planner   (round 3: CheckResult)
# ---------------------------------------------------------------------------

class TeacherResult(BaseModel):
    """The result of the teacher agent's attempt to teach a step"""

    step: str = Field(description="The step that the teacher agent attempted to teach.")

    explanation: str = Field(
        description="The explanation that the teacher agent provided for the step."
    )

    image_prompt: Optional[str] = Field(
        None,
        description="Usually empty. Fill in only when this step is about something visual that words "
        "explain badly (a spatial layout, a multi-stage process, a physical object): a short description "
        "of the image to draw. Never for definitions or abstract ideas. When in doubt, leave it empty.",
    )


class TaughtStep(TeacherResult):
    """A TeacherResult plus what the teacher node added after the model answered.
    Kept separate so the model never sees or fills these fields."""

    image: Optional[str] = Field(None, description="File name of the generated image, if one was made.")
    index: int = Field(description="Position of this step in the plan (0-based); teachers run in parallel and finish in any order.")

# ---------------------------------------------------------------------------
# Teacher -> Reviewer
# ---------------------------------------------------------------------------

class ReviewQuestion(BaseModel):
    """One multiple choice question checking understanding of a single taught step"""

    step: str = Field(description="The step that this question checks for understanding of.")

    question: str = Field(description="The multiple choice question to ask the student.")

    choices: list[str] = Field(
        description="Exactly 4 possible answers, one correct and 3 wrong answers based on common misconceptions about the step (or plausible wrong answers if there are none), in a random order."
    )

    correct_answer: str = Field(
        description="The correct answer, copied exactly as it appears in choices."
    )

class ReviewerResult(BaseModel):
    """The questions the reviewer agent wrote to check for understanding of what was taught"""

    questions: list[ReviewQuestion] = Field(
        description="One multiple choice question for each step that was taught, in the same order as the steps."
    )

# ---------------------------------------------------------------------------
# Planner -> Method subgraph
# ---------------------------------------------------------------------------

class SelectMethodResult(BaseModel):
    """Which teaching method to use for this request, and why."""

    chosen_method: Literal["structured_lesson", "socratic", "worked_faded", "analogy_bridging"] = Field(
        description="The teaching method that fits this request."
    )
    request_type: Literal[
        "overview", "specific_confusion", "told_fact", "procedure", "abstract_concept", "unclear"
    ] = Field(
        description="The underlying type of request, even when the student names a teaching style."
    )
    reason: str = Field(description="One line explaining the choice.")

# ---------------------------------------------------------------------------
# Socratic subgraph
# ---------------------------------------------------------------------------

class DialogueTurn(BaseModel):
    """One message in a Socratic dialogue."""

    role: Literal["tutor", "student"]
    text: str


class SocraticTarget(BaseModel):
    """What the dialogue is leading to. Internal only, never shown to the student."""

    target_insight: str = Field(description="The key insight, in one or two sentences.")
    premises: list[str] = Field(
        default_factory=list, description="The facts the student needs in order to reason their way to the insight."
    )
    misconceptions: list[str] = Field(
        default_factory=list, description="Common misconceptions to watch for on the way to the insight."
    )


class SocraticQuestion(BaseModel):
    """The next thing the tutor says to the student."""

    question: str = Field(description="One question or small hint for the student.")


class AnswerEvaluation(BaseModel):
    """How the student's latest answer relates to the target insight."""

    verdict: Literal["correct", "partial", "misconception", "stuck"] = Field(
        description="'correct' if the answer is right, 'partial' if it is right but incomplete, "
        "'misconception' if it rests on a wrong idea, 'stuck' if the student has no idea or didn't try."
    )
    reached_target: bool = Field(
        description="True only when the student has now expressed the target insight in their own words."
    )


class SocraticWrapUp(BaseModel):
    """How the dialogue ends."""

    explanation: str = Field(description="The insight in plain words.")
    terms: list[str] = Field(
        default_factory=list,
        description="Names and definitions the student couldn't have derived, each as 'name: definition'.",
    )

# ---------------------------------------------------------------------------
# Student -> Follow-up (after the lesson, outside the graph)
# ---------------------------------------------------------------------------

class FollowUpResult(BaseModel):
    """The answer to a student's follow-up question about one taught step"""

    answer: str = Field(description="A short, easy to follow answer to the student's question about this step.")


class FollowUp(BaseModel):
    """A follow-up question and its answer, saved with the session"""

    index: int = Field(description="Position of the step it was asked about (0-based).")
    question: str
    answer: str

# ---------------------------------------------------------------------------
# Reviewer -> Grader -> Reteacher -> Grader ...   (the quiz rounds)
# ---------------------------------------------------------------------------

class QuizQuestion(ReviewQuestion):
    """A ReviewQuestion tied to the plan step it checks; the index is added by code, never by the model."""

    index: int = Field(description="Position of the step this question checks (0-based).")


class GradedAnswer(BaseModel):
    """How the student did on one quiz question, filled in by the grader node (plain Python, no model)."""

    index: int = Field(description="Position of the step the question checks (0-based).")
    step: str
    question: str
    choices: list[str]
    picked: str
    correct_answer: str
    is_correct: bool


class GraderResult(BaseModel):
    """One graded quiz round: round 1 is the reviewer's quiz, later rounds re-check retaught steps."""

    round: int
    answers: list[GradedAnswer]


class ReteachResult(BaseModel):
    """A second try at teaching a step the student got wrong, aimed at the misconception behind their answer"""

    misconception: str = Field(
        description="In one or two sentences, what the student probably believes, judging by the wrong answer "
        "they picked, written to the student (e.g. 'You might be thinking that...')."
    )
    explanation: str = Field(
        description="A new explanation of the step that clears up that misconception, from a different angle "
        "than the explanations the student already read."
    )
    question: ReviewQuestion = Field(
        description="A new multiple choice question on the same step, different from the one they missed, "
        "to check whether the misconception is cleared up."
    )


class RetaughtStep(ReteachResult):
    """A ReteachResult plus what the reteacher node added after the model answered."""

    step: str = Field(description="The plan step that was retaught.")
    index: int = Field(description="Position of that step in the plan (0-based).")
    round: int = Field(description="The quiz round whose miss caused this reteach.")

# ---------------------------------------------------------------------------
# Worked-faded subgraph
# ---------------------------------------------------------------------------

class FadedStep(BaseModel):
    """One step of a solved problem."""

    task: str = Field(description="What this step has to do, without giving away its result.")
    work: str = Field(description="The step carried out, in plain text.")
    why: str = Field(description="One line on why this step works.")


class FadedProblem(BaseModel):
    """A problem and its solved steps."""

    problem: str = Field(description="The problem to solve, in plain text.")
    steps: list[FadedStep] = Field(description="The solution, as 3 or 4 steps in order.")
    why_question: str = Field(description="One question asking why a specific step of this solution works.")


class StepEvaluation(BaseModel):
    """Whether the student's answer is right, and what to tell them."""

    correct: bool = Field(description="True if the answer does what the step requires, even if worded differently.")
    feedback: str = Field(description="One line of feedback for the student.")


class FadedWrapUp(BaseModel):
    """How a worked-faded lesson ends."""

    text: str = Field(description="The closing message to the student.")

# ---------------------------------------------------------------------------
# Analogy-bridging subgraph
# ---------------------------------------------------------------------------

class AnalogyLesson(BaseModel):
    """A concept taught through something the student already knows."""

    analogy: str = Field(description="The everyday thing being compared to the concept.")
    explanation: str = Field(description="The concept explained through the analogy.")
    mapping: list[str] = Field(description="Each pair, written as 'this part of the analogy = this part of the concept'.")
    limits: str = Field(description="Where the analogy breaks down, so the student doesn't carry over wrong ideas.")


class ReexplainResult(BaseModel):
    """One more explanation covering what the check found missing."""

    text: str = Field(description="The re-explanation, written to the student.")

# ---------------------------------------------------------------------------
# Understanding checks
# ---------------------------------------------------------------------------

class CheckResult(BaseModel):
    """What every understanding check writes when it finishes."""

    check_type: str
    passed: bool
    gaps: list[str]


class PickCheckResult(BaseModel):
    """Which understanding check to run, and why."""

    check: Literal["quiz", "retrieval_practice", "teach_back", "erroneous_examples"] = Field(
        description="The check that will most effectively show whether the student understood."
    )
    reason: str = Field(description="One line explaining the choice.")


class GapEvaluation(BaseModel):
    """What a check found missing from the student's answer."""

    gaps: list[str] = Field(
        default_factory=list, description="Each thing the student missed or got wrong, one short line each. Empty if none."
    )


class TeachBackTurn(BaseModel):
    """The confused student's next move."""

    follow_up: Optional[str] = Field(None, description="The next naive question, or empty to stop asking.")


class ErroneousExample(BaseModel):
    """A solution or explanation with one planted mistake."""

    example: str = Field(description="The solution or explanation shown to the student, containing the mistake.")
    mistake: str = Field(description="What the mistake is and how to fix it. Never shown to the student.")
