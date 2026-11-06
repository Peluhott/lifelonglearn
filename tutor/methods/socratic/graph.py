from langgraph.graph import END, START, StateGraph

from tutor.methods.socratic.nodes import (
    SocraticState,
    after_evaluation,
    ask_question_node,
    evaluate_answer_node,
    give_hint_node,
    set_target_node,
    wait_for_answer_node,
    wrap_up_node,
)


def build_graph():
    """Lead the student to the key insight one question at a time. Inherits the parent's checkpointer."""
    builder = StateGraph(SocraticState)
    builder.add_node("set_target", set_target_node)
    builder.add_node("ask_question", ask_question_node)
    builder.add_node("wait_for_answer", wait_for_answer_node)
    builder.add_node("evaluate_answer", evaluate_answer_node)
    builder.add_node("give_hint", give_hint_node)
    builder.add_node("wrap_up", wrap_up_node)

    builder.add_edge(START, "set_target")
    builder.add_edge("set_target", "ask_question")
    builder.add_edge("ask_question", "wait_for_answer")
    builder.add_edge("wait_for_answer", "evaluate_answer")
    builder.add_conditional_edges("evaluate_answer", after_evaluation, ["ask_question", "give_hint", "wrap_up"])
    builder.add_edge("give_hint", "wait_for_answer")
    builder.add_edge("wrap_up", END)
    return builder.compile()
