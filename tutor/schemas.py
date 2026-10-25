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