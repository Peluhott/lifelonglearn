from langgraph.graph import END, START, StateGraph

from tutor.checks.context import wait_for_answer_node
from tutor.checks.erroneous_examples.nodes import ErroneousState, check_result_node, plant_mistake_node
from tutor.state import CheckOutput


def build_graph():
    """The student finds and fixes one planted mistake."""
    builder = StateGraph(ErroneousState, output_schema=CheckOutput)
    builder.add_node("plant_mistake", plant_mistake_node)
    builder.add_node("wait_for_answer", wait_for_answer_node)
    builder.add_node("check_result", check_result_node)

    builder.add_edge(START, "plant_mistake")
    builder.add_edge("plant_mistake", "wait_for_answer")
    builder.add_edge("wait_for_answer", "check_result")
    builder.add_edge("check_result", END)
    return builder.compile()
