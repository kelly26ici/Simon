# src/messages/chats/conversation.py

from src.configs.settings import MAX_HISTORY, CONVERSATION_TTL_SECONDS
from src.core.redis import RedisStore

_conversations = RedisStore(prefix="history")

async def get_history(sender: str) -> list[dict]:
    """Returns this customer's history list (creating it on first contact)."""
    history = await _conversations.get(sender)
    if history is None:
        history = []
        await _conversations.set(sender, history, ex=CONVERSATION_TTL_SECONDS)
    return history


async def append_message(sender: str, role: str, content: str):
    history = await get_history(sender)

    history.append(
        {
            "role": role,
            "content": [
                {
                    "type": "input_text" if role == "user" else "input_text",
                    "text": content,
                }
            ],
        }
    )

    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    await _conversations.set(sender, history, ex=CONVERSATION_TTL_SECONDS)


async def append_interaction_steps(sender: str, steps) -> None:
    """
    Stores Gemini returned interaction steps without changing them.
    Needed later for tool calling/function calling support.
    """

    history = await get_history(sender)

    history.extend(
        step.model_dump() if hasattr(step, "model_dump") else step
        for step in steps
    )

    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    await _conversations.set(sender, history, ex=CONVERSATION_TTL_SECONDS)