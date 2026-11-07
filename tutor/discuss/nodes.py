from langgraph.graph import END
from langgraph.types import interrupt

from tutor import llm, prompts
from tutor.checks.context import check_context
from tutor.schemas import DialogueTurn, DiscussReply
from tutor.state import DiscussState, TutorState

OPENING = "Anything you'd like to ask about this? Keep asking, or tell me when you'd like a test or you're done."

DISCUSS_REPLY_INSTRUCTIONS = prompts.load("discuss_reply")


def wait_for_message_node(state: DiscussState) -> dict:
    # kept apart from discuss_reply because this node reruns from the top on resume
    turns = state.get("discuss", [])
    message = interrupt({"question": turns[-1].text if turns else OPENING, "discuss": True})
    if isinstance(message, dict):  # the Test me and I'm done buttons skip the model
        return {"discuss_next": message["choice"]}
    return {"last_message": message, "discuss": [DialogueTurn(role="student", text=message)]}


def discuss_reply_node(state: DiscussState) -> dict:
    dialogue = "\n".join(f"{turn.role}: {turn.text}" for turn in state["discuss"])
    result = llm.structured(
        system=DISCUSS_REPLY_INSTRUCTIONS,
        content=f"{check_context(state)}\n\nThe conversation so far:\n{dialogue}",
        schema=DiscussReply,
    )
    return {"discuss": [DialogueTurn(role="tutor", text=result.text)], "discuss_next": result.next}


def after_message(state: DiscussState) -> str:
    # a typed message leaves the last reply's "continue" in place, so only a button's choice ends the chat here
    return END if state.get("discuss_next") in ("test", "finish") else "discuss_reply"


def after_reply(state: DiscussState) -> str:
    return "wait_for_message" if state["discuss_next"] == "continue" else END


def after_discuss(state: TutorState) -> str:
    return "pick_check" if state["discuss_next"] == "test" else "finish"
