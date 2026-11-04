from langgraph.graph import END, START, StateGraph

from tutor.methods.structured_lesson.nodes import finish_node, reviewer_node, teach_every_step, teacher_node
from tutor.state import TutorState


def build_graph():
    """Teach every plan step in parallel, then write the quiz. Inherits the parent's checkpointer."""
    builder = StateGraph(TutorState)
    builder.add_node("teacher", teacher_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("finish", finish_node)

    builder.add_conditional_edges(START, teach_every_step, ["teacher", "reviewer"])
    builder.add_edge("teacher", "reviewer")  # waits for every parallel teacher to finish, then runs once
    builder.add_edge("reviewer", "finish")
    builder.add_edge("finish", END)
    return builder.compile()
