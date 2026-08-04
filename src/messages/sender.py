# src/messages/sender.py

import httpx
import loguru
from src.clients.httpx_client import httpx as shared_httpx
from src.configs.settings import (
    META_ACCESS_TOKEN,
    META_GRAPH_API_VERSION,
    META_GRAPH_BASE_URL,
    META_PHONE_NUMBER_ID,
)

logger = loguru.logger


def _get_headers() -> dict[str, str]:
    """Builds standard authorization headers for Graph API requests."""
    return {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def _get_messages_url() -> str:
    """Constructs the base WhatsApp messages endpoint."""
    return f"{META_GRAPH_BASE_URL}/{META_GRAPH_API_VERSION}/{META_PHONE_NUMBER_ID}/messages"


async def send_whatsapp_message(to: str, text: str) -> None:
    """Sends a text message to a specific WhatsApp recipient."""
    url = _get_messages_url()
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    log = logger.bind(recipient=to, action="send_whatsapp_message")

    try:
        resp = await shared_httpx.post(url, headers=_get_headers(), json=payload)
        resp.raise_for_status()

        data = resp.json()
        meta_msg_id = data.get("messages", [{}])[0].get("id")
        log.bind(wa_mid=meta_msg_id, status_code=resp.status_code).info(
            "WhatsApp message delivered successfully"
        )

    except httpx.HTTPStatusError as exc:
        # Extracts Meta's rich JSON error response
        try:
            error_details = exc.response.json().get("error", {})
        except Exception:
            error_details = {"raw": exc.response.text}

        log.bind(
            status_code=exc.response.status_code,
            error_code=error_details.get("code"),
            error_subcode=error_details.get("error_subcode"),
            fbtrace_id=error_details.get("fbtrace_id"),
            error_details=error_details,
        ).error(f"Meta Graph API error: {error_details.get('message', exc)}")
        raise

    except httpx.TimeoutException:
        log.error("Request timed out while sending WhatsApp message")
        raise

    except httpx.RequestError as exc:
        log.error(f"Network error sending message to {to}: {exc}")
        raise


async def send_typing_indicator(message_id: str) -> None:
    """Marks the inbound message as read and displays the typing bubble."""
    url = _get_messages_url()
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"},
    }

    log = logger.bind(target_msg_id=message_id, action="send_typing_indicator")

    try:
        resp = await shared_httpx.post(url, headers=_get_headers(), json=payload)
        resp.raise_for_status()

        log.bind(status_code=resp.status_code).debug(
            "Typing indicator & read status set"
        )

    except httpx.HTTPStatusError as exc:
        try:
            error_details = exc.response.json().get("error", {})
        except Exception:
            error_details = {"raw": exc.response.text}

        log.bind(
            status_code=exc.response.status_code,
            error_code=error_details.get("code"),
            error_details=error_details,
        ).warning(
            f"Failed to set typing indicator: {error_details.get('message', exc)}"
        )
        # Note: We don't raise here so typing indicator failures don't break message delivery pipeline

    except httpx.RequestError as exc:
        log.warning(f"Network warning setting typing indicator: {exc}")
