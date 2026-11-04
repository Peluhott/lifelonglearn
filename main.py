import uuid

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from api import db
from tutor.graph import build_graph

# pausing for the student's answers needs a checkpointer; in memory is enough for one run
graph = build_graph(InMemorySaver(serde=db.serializer()))
config = {"configurable": {"thread_id": str(uuid.uuid4())}}

prompt = input("What are you stuck on?\n> ")
final_state = graph.invoke({"user_prompt": prompt}, config)
while "__interrupt__" in final_state:
    question = final_state["__interrupt__"][0].value["question"]
    final_state = graph.invoke(Command(resume=input(f"{question}\n> ")), config)

print(final_state["intake"].model_dump_json(indent=2))
print(final_state["planner"].model_dump_json(indent=2))
print(final_state["select_method"].model_dump_json(indent=2))
for result in sorted(final_state.get("teacher", []), key=lambda t: t.index):  # teachers run in parallel, so restore plan order
    print(result.model_dump_json(indent=2))
if final_state.get("socratic"):
    print(final_state["socratic"][-1].text)  # the wrap-up
print(f"Finished: {final_state['outcome']}")
if "reviewer" in final_state:
    print(final_state["reviewer"].model_dump_json(indent=2))
