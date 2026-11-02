from tutor.graph import graph

prompt = input("What are you stuck on?\n> ")
final_state = graph.invoke({"user_prompt": prompt})
print(final_state["intake"].model_dump_json(indent=2))
print(final_state["planner"].model_dump_json(indent=2))
for result in sorted(final_state.get("teacher", []), key=lambda t: t.index):  # teachers run in parallel, so restore plan order
    print(result.model_dump_json(indent=2))
print("All steps covered")
if "reviewer" in final_state:
    print(final_state["reviewer"].model_dump_json(indent=2))
