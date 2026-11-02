import operator
from typing import Annotated, TypedDict

from tutor.schemas import IntakeResult
from tutor.schemas import PlannerResult
from tutor.schemas import TaughtStep
from tutor.schemas import ReviewerResult
# a shared state between agents, as we add more agents it will grow and more fields will be added
class TutorState(TypedDict, total=False):
    user_prompt: str          # what the student typed
    intake: IntakeResult      # filled in by the intake agent
    planner: PlannerResult    # filled in by the planner agent
    teacher: Annotated[list[TaughtStep], operator.add]  # one result per step, appended by the parallel teachers in any order (use .index)
    reviewer: ReviewerResult  # the questions the reviewer agent wrote, one per taught step


class TeacherTask(TypedDict):
    """What each parallel teacher gets instead of the shared state (sent by graph.teach_every_step)."""
    planner: PlannerResult
    step_index: int
