from langgraph.graph import END, START, StateGraph

from tutor.methods.worked_faded.nodes import (
    WorkedFadedState,
    after_step,
    ask_step_node,
    evaluate_step_node,
    faded_wrap_up_node,
    next_problem_node,
    wait_for_step_node,
)


def build_graph():
    """Show a solved problem, then leave more of each new one to the student. Inherits the parent's checkpointer."""
    builder = StateGraph(WorkedFadedState)
    builder.add_node("next_problem", next_problem_node)
    builder.add_node("ask_step", ask_step_node)
    builder.add_node("wait_for_step", wait_for_step_node)
    builder.add_node("evaluate_step", evaluate_step_node)
    builder.add_node("faded_wrap_up", faded_wrap_up_node)

    builder.add_edge(START, "next_problem")
    builder.add_edge("next_problem", "ask_step")
    builder.add_edge("ask_step", "wait_for_step")
    builder.add_edge("wait_for_step", "evaluate_step")
    builder.add_conditional_edges("evaluate_step", after_step, ["ask_step", "next_problem", "faded_wrap_up"])
    builder.add_edge("faded_wrap_up", END)
    return builder.compile()
