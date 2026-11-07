import operator
from typing import Annotated, TypedDict

from tutor.schemas import AnalogyLesson
from tutor.schemas import CheckResult
from tutor.schemas import DialogueTurn
from tutor.schemas import IntakeResult
from tutor.schemas import PickCheckResult
from tutor.schemas import PlannerResult
from tutor.schemas import SelectMethodResult
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
    select_method: SelectMethodResult  # which teaching method runs, filled in by the select_method node
    teacher: Annotated[list[TaughtStep], operator.add]  # one result per step, appended by the parallel teachers in any order (use .index)
    reviewer: ReviewerResult  # the questions the reviewer agent wrote, one per taught step
    socratic: Annotated[list[DialogueTurn], operator.add]  # the dialogue, shared so a finished session can reopen
    outcome: str              # "completed" or "stuck", set by whichever method ran
    discuss: Annotated[list[DialogueTurn], operator.add]  # the chat after a lesson, so it can reopen
    discuss_next: str         # how the chat left things: "continue", "test" or "finish"
    pick_check: PickCheckResult  # which understanding check runs and why
    check_result: CheckResult    # whether the student passed, and the gaps
    check_turns: Annotated[list[DialogueTurn], operator.add]  # prompts and answers of a text check, so it can reopen
    worked_faded: Annotated[list[DialogueTurn], operator.add]  # the worked-faded dialogue, so it can reopen
    analogy_bridging: AnalogyLesson  # the analogy lesson
    reexplain: str            # the one re-explanation after a check found gaps
    grader: Annotated[list[GraderResult], operator.add]  # one graded quiz round per entry, in order
    reteacher: Annotated[list[RetaughtStep], operator.add]  # reteaches of missed steps, across all rounds (use .round / .index)


class CheckOutput(TypedDict, total=False):
    """All a check hands back to its method. Without this, a check built on TutorState would also return the
    method's whole `teacher` list when it finishes, and the reducer would append every lesson a second time."""
    check_result: CheckResult
    check_turns: Annotated[list[DialogueTurn], operator.add]
    reviewer: ReviewerResult
    grader: Annotated[list[GraderResult], operator.add]
    reteacher: Annotated[list[RetaughtStep], operator.add]


class CheckState(TutorState, total=False):
    """TutorState plus what the text checks keep to themselves."""
    last_answer: str


class DiscussOutput(TypedDict, total=False):
    """All the discussion hands back to its method, for the same reason as CheckOutput."""
    discuss: Annotated[list[DialogueTurn], operator.add]
    discuss_next: str


class DiscussState(TutorState, total=False):
    """TutorState plus what the discussion keeps to itself."""
    last_message: str


class TeacherTask(TypedDict):
    """What each parallel teacher gets instead of the shared state (sent by teach_every_step)."""
    planner: PlannerResult
    step_index: int


class ReteachTask(TypedDict):
    """What each parallel reteacher gets (sent by reteach_missed)."""
    planner: PlannerResult
    step: TaughtStep
    graded: GradedAnswer           # the question they missed and what they picked
    earlier: list[RetaughtStep]    # earlier reteaches of this step, so a retry takes a new angle
    round: int
