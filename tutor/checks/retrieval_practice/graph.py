from langgraph.graph import END, START, StateGraph

from tutor.checks.context import wait_for_answer_node
from tutor.checks.retrieval_practice.nodes import ask_recall_node, check_result_node
from tutor.state import CheckOutput, CheckState


def build_graph():
    """The student writes the key points from memory; what's missing compared to the lesson is the gaps."""
    builder = StateGraph(CheckState, output_schema=CheckOutput)
    builder.add_node("ask_recall", ask_recall_node)
    builder.add_node("wait_for_answer", wait_for_answer_node)
    builder.add_node("check_result", check_result_node)

    builder.add_edge(START, "ask_recall")
    builder.add_edge("ask_recall", "wait_for_answer")
    builder.add_edge("wait_for_answer", "check_result")
    builder.add_edge("check_result", END)
    return builder.compile()
