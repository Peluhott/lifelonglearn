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
    