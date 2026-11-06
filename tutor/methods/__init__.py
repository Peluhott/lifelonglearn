from tutor.methods.analogy_bridging.graph import build_graph as build_analogy_bridging
from tutor.methods.socratic.graph import build_graph as build_socratic
from tutor.methods.structured_lesson.graph import build_graph as build_structured_lesson
from tutor.methods.worked_faded.graph import build_graph as build_worked_faded

# method name -> function that compiles its subgraph; the parent graph adds a node and a route for each
METHODS = {
    "structured_lesson": build_structured_lesson,
    "socratic": build_socratic,
    "worked_faded": build_worked_faded,
    "analogy_bridging": build_analogy_bridging,
}
