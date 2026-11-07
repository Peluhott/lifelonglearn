from langgraph.graph import END, START, StateGraph

from tutor.discuss.nodes import after_discuss, after_message, after_reply, discuss_reply_node, wait_for_message_node
from tutor.state import DiscussOutput, DiscussState


def build_graph():
    """Chat about the lesson until the student wants a test or is done."""
    builder = StateGraph(DiscussState, output_schema=DiscussOutput)
    builder.add_node("wait_for_message", wait_for_message_node)
    builder.add_node("discuss_reply", discuss_reply_node)

    builder.add_edge(START, "wait_for_message")
    builder.add_conditional_edges("wait_for_message", after_message, ["discuss_reply", END])
    builder.add_conditional_edges("discuss_reply", after_reply, ["wait_for_message", END])
    return builder.compile()


def add_discussion(builder) -> None:
    """Add the discussion to a method that already has `pick_check` (from add_checks) and `finish` nodes."""
    builder.add_node("discuss", build_graph())
    builder.add_conditional_edges("discuss", after_discuss, ["pick_check", "finish"])
