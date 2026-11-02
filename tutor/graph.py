from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from tutor.agents.intake import intake_node
from tutor.agents.planner import planner_node
from tutor.agents.teacher import teacher_node
from tutor.agents.reviewer import reviewer_node
from tutor.state import TutorState


def teach_every_step(state: TutorState):
    """Start one teacher per plan step, all at once; with no steps, go straight to the reviewer."""
    plan = state["planner"]
    if not plan.steps:
        return "reviewer"
    # each Send runs the teacher with its own small input instead of the shared state
    return [Send("teacher", {"planner": plan, "step_index": i}) for i in range(len(plan.steps))]

# register state in graph
builder = StateGraph(TutorState)        # a graph whose shared state is TutorState


#register the agents as nodes in the graph
builder.add_node("intake", intake_node) # register intake
builder.add_node("planner", planner_node) # register planner
builder.add_node("teacher", teacher_node) # register teacher
builder.add_node("reviewer", reviewer_node) # register reviewer



#start mapping out the graph
builder.add_edge(START, "intake")       # first thing that runs
builder.add_edge("intake", "planner")
builder.add_conditional_edges("planner", teach_every_step, ["teacher", "reviewer"])
builder.add_edge("teacher", "reviewer")  # waits for every parallel teacher to finish, then runs once
builder.add_edge("reviewer", END)


def build_graph(checkpointer=None):
    """Compile the graph; with a checkpointer, every run's state is saved under its thread_id."""
    return builder.compile(checkpointer=checkpointer)


graph = build_graph()                   # no saving: used by the CLI and tests
