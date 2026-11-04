from tutor.methods.socratic.graph import build_graph as build_socratic
from tutor.methods.structured_lesson.graph import build_graph as build_structured_lesson

# method name -> function that compiles its subgraph; the parent graph adds a node and a route for each
METHODS = {
    "structured_lesson": build_structured_lesson,
    "socratic": build_socratic,
}
