from langgraph.graph import END, START, StateGraph

from tutor.checks.quiz.grader import grader_node
from tutor.checks.quiz.nodes import check_result_node, reteach_missed, reviewer_node
from tutor.checks.quiz.reteacher import reteacher_node
from tutor.state import CheckOutput, TutorState


def build_graph():
    """Multiple choice rounds, reteaching what was missed until it's right or the retries run out."""
    builder = StateGraph(TutorState, output_schema=CheckOutput)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("grader", grader_node)
    builder.add_node("reteacher", reteacher_node)
    builder.add_node("check_result", check_result_node)

    builder.add_edge(START, "reviewer")
    builder.add_edge("reviewer", "grader")  # the grader pauses (interrupt) until the student's answers come back
    builder.add_conditional_edges("grader", reteach_missed, ["reteacher", "check_result"])
    builder.add_edge("reteacher", "grader")  # waits for every parallel reteacher, then quizzes the retaught steps
    builder.add_edge("check_result", END)
    return builder.compile()
