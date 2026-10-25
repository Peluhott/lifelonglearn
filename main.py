from tutor.graph import graph

prompt = input("What are you stuck on?\n> ")
final_state = graph.invoke({"user_prompt": prompt})
print(final_state["intake"].model_dump_json(indent=2))
print(final_state["planner"].model_dump_json(indent=2))