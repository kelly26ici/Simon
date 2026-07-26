# src/messages/chats/conversations.py

from src.configs.settings import MAX_HISTORY

_conversations: dict[str, list[dict]] = {}


def get_history(sender: str) -> list[dict]:
    """Returns this customer's history list (creating it on first contact)."""
    return _conversations.setdefault(sender, [])


def append_message(sender: str, role: str, content: str):
    history = get_history(sender)

    history.append(
        {
            "role": role,
            "content": [
                {
                    "type": "input_text" if role == "user" else "output_text",
                    "text": content,
                }
            ],
        }
    )

    if len(history) > MAX_HISTORY:
        _conversations[sender] = history[-MAX_HISTORY:]

def append_interaction_steps(sender: str, steps) -> None:
    """
    Stores Gemini returned interaction steps without changing them.
    Needed later for tool calling/function calling support.
    """

    history = get_history(sender)

    history.extend(
        step.model_dump() if hasattr(step, "model_dump") else step
        for step in steps
    )

    if len(history) > MAX_HISTORY:
        _conversations[sender] = history[-MAX_HISTORY:]