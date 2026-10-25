from tutor import llm 
from tutor.schemas import PlannerResult
from tutor.state import TutorState

PLANNER_INSTRUCTIONS = """ You are the planner step of a tutoring system,
your job is to take the output of the intake step and decide what to do, you will recieve
the task type which is what you need to do, the target concept which is the main concept that you
need to create a plan for, the mentioned concepts which are other concepts that are related
there will be a confusion type which will either be specific to make it easier for you to create a plan
or everything which means the student is confused about everything and will have to create a plan that covers.
for the plan break down the concept into steps or pieces that make up that larger concept that logically follow the other"""

def planner_node(state: TutorState) -> dict:
    result = llm.structured(
        system=PLANNER_INSTRUCTIONS,
        content=state["intake"].model_dump_json(),
        schema=PlannerResult,
    )
    return {"planner": result}
