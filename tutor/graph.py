from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from tutor.agents.intake import intake_node
from tutor.agents.planner import planner_node
from tutor.agents.select_method import select_method_node
from tutor.methods import METHODS
from tutor.serde import serializer
from tutor.state import TutorState


def route_to_method(state: TutorState) -> str:
    return state["select_method"].chosen_method

# register state in graph
builder = StateGraph(TutorState)        # a graph whose shared state is TutorState


#register the agents as nodes in the graph
builder.add_node("intake", intake_node) # register intake
builder.add_node("planner", planner_node) # register planner
builder.add_node("select_method", select_method_node) # register select_method
for name, build_method in METHODS.items():
    builder.add_node(name, build_method())  # each teaching method is a compiled subgraph
    builder.add_edge(name, END)



#start mapping out the graph
builder.add_edge(START, "intake")       # first thing that runs
builder.add_edge("intake", "planner")
builder.add_edge("planner", "select_method")
builder.add_conditional_edges("select_method", route_to_method, list(METHODS))


def build_graph(checkpointer=None):
    """Compile the graph; with a checkpointer, every run's state is saved under its thread_id."""
    return builder.compile(checkpointer=checkpointer)


def method_values(snapshot) -> dict:
    """Session state from `get_state(config, subgraphs=True)`.

    A subgraph only hands its shared keys to the parent when it finishes, so while a method is
    paused or has failed, what it has produced so far is only in the subgraph's own state.
    """
    values = dict(snapshot.values)
    for task in snapshot.tasks:
        if task.state:
            values.update(method_values(task.state))
    return values


def live_snapshot(snapshot):
    """The innermost running subgraph's snapshot from `get_state(config, subgraphs=True)`.

    Read `.interrupts` here, not on the parent: the parent keeps reporting an interrupt its
    subgraph has already moved past, until the subgraph finishes.
    """
    for task in snapshot.tasks:
        if task.state:
            return live_snapshot(task.state)
    return snapshot


graph = build_graph(InMemorySaver(serde=serializer()))  # CLI and tests; interrupts need a checkpointer, so pass a thread_id
