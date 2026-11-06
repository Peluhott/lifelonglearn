from langgraph.graph import END, START, StateGraph

from tutor.checks import add_checks
from tutor.methods.structured_lesson.nodes import finish_node, teach_every_step, teacher_node
from tutor.state import TutorState


def build_graph():
    """Teach every plan step in parallel, then run one understanding check. Inherits the parent's checkpointer."""
    builder = StateGraph(TutorState)
    builder.add_node("teacher", teacher_node)
    builder.add_node("finish", finish_node)
    add_checks(builder, "finish")

    builder.add_conditional_edges(START, teach_every_step, ["teacher", "finish"])
    builder.add_edge("teacher", "pick_check")  # waits for every parallel teacher to finish, then runs once
    builder.add_edge("finish", END)
    return builder.compile()
