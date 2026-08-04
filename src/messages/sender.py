# src/messages/sender.

from src.clients.httpx_client import httpx
from src.configs.settings import (
    META_ACCESS_TOKEN,
    META_PHONE_NUMBER_ID,
    META_GRAPH_API_VERSION,
    META_GRAPH_BASE_URL,
)


async def send_whatsapp_message(to: str, text: str) -> None:
    url = f"{META_GRAPH_BASE_URL}/{META_GRAPH_API_VERSION}/{META_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",

        "text": {"body": text},
    }
    resp = await httpx.post(url, headers=headers, json=payload)
    print("Send status:", resp.status_code, resp.text)

# src/messages/sender.py

async def send_typing_indicator(message_id: str) -> None:
    """Marks the inbound message as read and shows the typing bubble.
    Auto-dismisses after 25s or as soon as the actual reply is sent.
    """
    url = f"{META_GRAPH_BASE_URL}/{META_GRAPH_API_VERSION}/{META_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=HEADERS, json=payload)
        resp.raise_for_status()# src/messages/sender.py

