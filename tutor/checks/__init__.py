from tutor.checks.erroneous_examples.graph import build_graph as build_erroneous_examples
from tutor.checks.pick_check import pick_check_node, route_to_check
from tutor.checks.quiz.graph import build_graph as build_quiz
from tutor.checks.retrieval_practice.graph import build_graph as build_retrieval_practice
from tutor.checks.teach_back.graph import build_graph as build_teach_back

# check name -> function that compiles its subgraph; the names must match PickCheckResult.check
CHECKS = {
    "quiz": build_quiz,
    "retrieval_practice": build_retrieval_practice,
    "teach_back": build_teach_back,
    "erroneous_examples": build_erroneous_examples,
}


def add_checks(builder, next_node, path=None) -> None:
    """Add pick_check and every check to a method. next_node is the node to go to next, or with `path`
    (the nodes it can return) a function that chooses it."""
    builder.add_node("pick_check", pick_check_node)
    builder.add_conditional_edges("pick_check", route_to_check, list(CHECKS))
    for name, build_check in CHECKS.items():
        builder.add_node(name, build_check())
        if path:
            builder.add_conditional_edges(name, next_node, path)
        else:
            builder.add_edge(name, next_node)
