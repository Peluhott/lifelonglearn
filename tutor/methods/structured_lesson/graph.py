from langgraph.graph import END, START, StateGraph

from tutor.methods.structured_lesson.grader import grader_node
from tutor.methods.structured_lesson.nodes import finish_node, reteach_missed, reviewer_node, teach_every_step, teacher_node
from tutor.methods.structured_lesson.reteacher import reteacher_node
from tutor.state import TutorState


def build_graph():
    """Teach every plan step in parallel, then quiz and reteach until done. Inherits the parent's checkpointer."""
    builder = StateGraph(TutorState)
    builder.add_node("teacher", teacher_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("grader", grader_node)
    builder.add_node("reteacher", reteacher_node)
    builder.add_node("finish", finish_node)

    builder.add_conditional_edges(START, teach_every_step, ["teacher", "reviewer"])
    builder.add_edge("teacher", "reviewer")  # waits for every parallel teacher to finish, then runs once
    builder.add_edge("reviewer", "grader")  # the grader pauses (interrupt) until the student's answers come back
    builder.add_conditional_edges("grader", reteach_missed, ["reteacher", "finish"])
    builder.add_edge("reteacher", "grader")  # waits for every parallel reteacher, then quizzes the retaught steps
    builder.add_edge("finish", END)
    return builder.compile()
