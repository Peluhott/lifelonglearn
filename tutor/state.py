import operator
from typing import Annotated, TypedDict

from tutor.schemas import IntakeResult
from tutor.schemas import PlannerResult
from tutor.schemas import TaughtStep
from tutor.schemas import ReviewerResult
from tutor.schemas import GradedAnswer
from tutor.schemas import GraderResult
from tutor.schemas import RetaughtStep
# a shared state between agents, as we add more agents it will grow and more fields will be added
class TutorState(TypedDict, total=False):
    user_prompt: str          # what the student typed
    intake: IntakeResult      # filled in by the intake agent
    planner: PlannerResult    # filled in by the planner agent
    teacher: Annotated[list[TaughtStep], operator.add]  # one result per step, appended by the parallel teachers in any order (use .index)
    reviewer: ReviewerResult  # the questions the reviewer agent wrote, one per taught step
    grader: Annotated[list[GraderResult], operator.add]  # one graded quiz round per entry, in order
    reteacher: Annotated[list[RetaughtStep], operator.add]  # reteaches of missed steps, across all rounds (use .round / .index)


class TeacherTask(TypedDict):
    """What each parallel teacher gets instead of the shared state (sent by graph.teach_every_step)."""
    planner: PlannerResult
    step_index: int


class ReteachTask(TypedDict):
    """What each parallel reteacher gets (sent by graph.reteach_missed)."""
    planner: PlannerResult
    step: TaughtStep
    graded: GradedAnswer           # the question they missed and what they picked
    earlier: list[RetaughtStep]    # earlier reteaches of this step, so a retry takes a new angle
    round: int
