from langgraph.graph import END, START, StateGraph

from tutor.agents.intake import intake_node
from tutor.agents.planner import planner_node
from tutor.agents.teacher import teacher_node
from tutor.agents.reviewer import reviewer_node
from tutor.state import TutorState


def has_steps_left(state: TutorState) -> str:
    """Send the graph back to the teacher until every planner step has been taught."""
    if state["planner_index"] < len(state["planner"].steps):
        return "teacher"
    return "reviewer"  # if there are no steps left, go to the reviewer to check for understanding

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
builder.add_conditional_edges("planner", has_steps_left)  # skip the teacher if the plan has no steps
builder.add_conditional_edges("teacher", has_steps_left)  # loop back to the teacher, or go to the reviewer when done
builder.add_edge("reviewer", END)       # reviewer runs once at the end, then we're done

graph = builder.compile()               # turn the blueprint into something runnable
