from langgraph.graph import END, START, StateGraph

from tutor.agents.intake import intake_node
from tutor.agents.planner import planner_node
from tutor.state import TutorState

builder = StateGraph(TutorState)        # a graph whose shared state is TutorState
builder.add_node("intake", intake_node) # register the agent under a name
builder.add_node("planner", planner_node)
builder.add_edge(START, "intake")
builder.add_edge("intake","planner")       # first thing that runs
builder.add_edge("planner", END)         # then stop

graph = builder.compile()               # turn the blueprint into something runnable