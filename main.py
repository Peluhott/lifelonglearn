from tutor.graph import graph

prompt = input("What are you stuck on?\n> ")
final_state = graph.invoke({"user_prompt": prompt}, config={"recursion_limit": 50})  # each teacher step counts toward the limit
print(final_state["intake"].model_dump_json(indent=2))
print(final_state["planner"].model_dump_json(indent=2))
for result in final_state.get("teacher", []):
    print(result.model_dump_json(indent=2))
print("All steps covered")
