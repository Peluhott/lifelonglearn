from langgraph.graph import END, START, StateGraph

from tutor.checks.context import wait_for_answer_node
from tutor.checks.teach_back.nodes import (
    TeachBackState,
    after_answer,
    after_follow_up,
    ask_to_explain_node,
    check_result_node,
    follow_up_node,
)
from tutor.state import CheckOutput


def build_graph():
    """The student explains the concept to a confused student, who asks naive follow-ups."""
    builder = StateGraph(TeachBackState, output_schema=CheckOutput)
    builder.add_node("ask_to_explain", ask_to_explain_node)
    builder.add_node("wait_for_answer", wait_for_answer_node)
    builder.add_node("follow_up", follow_up_node)
    builder.add_node("check_result", check_result_node)

    builder.add_edge(START, "ask_to_explain")
    builder.add_edge("ask_to_explain", "wait_for_answer")
    builder.add_conditional_edges("wait_for_answer", after_answer, ["follow_up", "check_result"])
    builder.add_conditional_edges("follow_up", after_follow_up, ["wait_for_answer", "check_result"])
    builder.add_edge("check_result", END)
    return builder.compile()
