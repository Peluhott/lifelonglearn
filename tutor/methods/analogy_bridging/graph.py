from langgraph.graph import END, START, StateGraph

from tutor.checks import add_checks
from tutor.discuss.graph import add_discussion
from tutor.methods.analogy_bridging.nodes import after_check, analogy_lesson_node, finish_node, reexplain_node
from tutor.state import TutorState


def build_graph():
    """Teach through an analogy and discuss it. A check runs only if the student wants one, and re-explains once if it
    found gaps. Inherits the parent's checkpointer."""
    builder = StateGraph(TutorState)
    builder.add_node("analogy_lesson", analogy_lesson_node)
    builder.add_node("reexplain", reexplain_node)
    builder.add_node("finish", finish_node)
    add_checks(builder, after_check, ["reexplain", "finish"])
    add_discussion(builder)

    builder.add_edge(START, "analogy_lesson")
    builder.add_edge("analogy_lesson", "discuss")
    builder.add_edge("reexplain", "finish")
    builder.add_edge("finish", END)
    return builder.compile()
