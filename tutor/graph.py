from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from tutor.agents.intake import intake_node
from tutor.agents.planner import planner_node
from tutor.agents.teacher import teacher_node
from tutor.agents.reviewer import reviewer_node
from tutor.agents.grader import grader_node
from tutor.agents.reteacher import reteacher_node
from tutor.serde import serializer
from tutor.state import TutorState

MAX_RETEACHES = 2  # per step; after that a missed step ends as "still needs work"


def teach_every_step(state: TutorState):
    """Start one teacher per plan step, all at once; with no steps, go straight to the reviewer."""
    plan = state["planner"]
    if not plan.steps:
        return "reviewer"
    # each Send runs the teacher with its own small input instead of the shared state
    return [Send("teacher", {"planner": plan, "step_index": i}) for i in range(len(plan.steps))]


def reteach_missed(state: TutorState):
    """After a graded round, reteach every missed step that still has retries left (in parallel); otherwise finish."""
    rounds = state.get("grader", [])
    if not rounds:
        return END
    latest = rounds[-1]
    taught = {t.index: t for t in state["teacher"]}
    retaught = state.get("reteacher", [])
    sends = []
    for graded in latest.answers:
        earlier = [r for r in retaught if r.index == graded.index]
        if not graded.is_correct and len(earlier) < MAX_RETEACHES:
            task = {"planner": state["planner"], "step": taught[graded.index], "graded": graded, "earlier": earlier, "round": latest.round}
            sends.append(Send("reteacher", task))
    return sends or END

# register state in graph
builder = StateGraph(TutorState)        # a graph whose shared state is TutorState


#register the agents as nodes in the graph
builder.add_node("intake", intake_node) # register intake
builder.add_node("planner", planner_node) # register planner
builder.add_node("teacher", teacher_node) # register teacher
builder.add_node("reviewer", reviewer_node) # register reviewer
builder.add_node("grader", grader_node)
builder.add_node("reteacher", reteacher_node)



#start mapping out the graph
builder.add_edge(START, "intake")       # first thing that runs
builder.add_edge("intake", "planner")
builder.add_conditional_edges("planner", teach_every_step, ["teacher", "reviewer"])
builder.add_edge("teacher", "reviewer")  # waits for every parallel teacher to finish, then runs once
builder.add_edge("reviewer", "grader")  # the grader pauses (interrupt) until the student's answers come back
builder.add_conditional_edges("grader", reteach_missed, ["reteacher", END])
builder.add_edge("reteacher", "grader")  # waits for every parallel reteacher, then quizzes the retaught steps


def build_graph(checkpointer=None):
    """Compile the graph; with a checkpointer, every run's state is saved under its thread_id."""
    return builder.compile(checkpointer=checkpointer)


graph = build_graph(InMemorySaver(serde=serializer()))  # CLI and tests; interrupts need a checkpointer, so pass a thread_id
