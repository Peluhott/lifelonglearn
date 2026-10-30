import operator
from typing import Annotated, TypedDict

from tutor.schemas import IntakeResult
from tutor.schemas import PlannerResult
from tutor.schemas import TeacherResult
from tutor.schemas import ReviewerResult
# a shared state between agents, as we add more agents it will grow and more fields will be added
class TutorState(TypedDict, total=False):
    user_prompt: str          # what the student typed
    intake: IntakeResult      # filled in by the intake agent
    planner: PlannerResult    # filled in by the planner agent
    teacher: Annotated[list[TeacherResult], operator.add]  # one result per step, appended by the teacher agent
    planner_index: int        # which step in planner.steps to teach next, set to 0 by planner and moved forward by teacher
    reviewer: ReviewerResult  # the questions the reviewer agent wrote, one per taught step
