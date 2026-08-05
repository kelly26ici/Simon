# src/messages/sender.py

import httpx
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from src.clients.httpx_client import get_http_client
from src.configs.settings import (
    META_ACCESS_TOKEN,
    META_GRAPH_API_VERSION,
    META_GRAPH_BASE_URL,
    META_PHONE_NUMBER_ID,
)
from src.messages.formatter import format_for_whatsapp

# Only retry genuine transient failures. HTTP status errors (bad auth,
# malformed payload, Meta-side validation errors) are not retryable.
_TRANSIENT_ERRORS = (httpx.TransportError, httpx.TimeoutException)


def _get_headers() -> dict[str, str]:
    """Builds standard authorization headers for Graph API requests."""
    return {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def _get_messages_url() -> str:
    """Constructs the base WhatsApp messages endpoint."""
    return f"{META_GRAPH_BASE_URL}/{META_GRAPH_API_VERSION}/{META_PHONE_NUMBER_ID}/messages"


def _extract_error_details(exc: httpx.HTTPStatusError) -> dict:
    """Extracts Meta's rich JSON error response from an HTTPStatusError."""
    try:
        return exc.response.json().get("error", {})
    except Exception:
        return {"raw": exc.response.text}


async def _send_single_message(to: str, text: str) -> str | None:
    """Sends a single WhatsApp text message (no formatting, no splitting).

    Returns the Meta message ID on success, or None on failure.
    """
    url = _get_messages_url()
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    log = logger.bind(recipient=to, action="send_whatsapp_message")

    try:
        client = get_http_client()
        resp = await client.post(url, headers=_get_headers(), json=payload)
        resp.raise_for_status()

        data = resp.json()
        meta_msg_id = data.get("messages", [{}])[0].get("id")
        log.bind(wa_mid=meta_msg_id, status_code=resp.status_code).info(
            "WhatsApp message delivered successfully"
        )
        return meta_msg_id

    except httpx.HTTPStatusError as exc:
        error_details = _extract_error_details(exc)

        log.bind(
            status_code=exc.response.status_code,
            error_code=error_details.get("code"),
            error_subcode=error_details.get("error_subcode"),
            fbtrace_id=error_details.get("fbtrace_id"),
            error_details=error_details,
        ).error(f"Meta Graph API error: {error_details.get('message', exc)}")
        raise

    except _TRANSIENT_ERRORS as exc:
        log.error(f"Transient error sending message to {to}: {exc}")
        raise


async def send_whatsapp_message(to: str, text: str) -> None:
    """Sends a text message to a specific WhatsApp recipient.

    The text is first passed through the WhatsApp formatting layer, which:
    - Converts Markdown to WhatsApp-compatible syntax
    - Converts tables to readable text grids
    - Splits long responses (>4096 chars) at paragraph boundaries

    If the formatted text is split into multiple parts, each part is sent
    as a separate WhatsApp message.
    """
    # Format the text through the WhatsApp formatting layer (single choke-point)
    messages = format_for_whatsapp(text)

    for msg in messages:
        await _send_single_message(to, msg)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(_TRANSIENT_ERRORS),
    before_sleep=before_sleep_log(logger, "WARNING"),
)
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
        client = get_http_client()
        resp = await client.post(url, headers=_get_headers(), json=payload)
        resp.raise_for_status()

        log.bind(status_code=resp.status_code).debug(
            "Typing indicator & read status set"
        )

    except httpx.HTTPStatusError as exc:
        error_details = _extract_error_details(exc)

        log.bind(
            status_code=exc.response.status_code,
            error_code=error_details.get("code"),
            error_details=error_details,
        ).warning(
            f"Failed to set typing indicator: {error_details.get('message', exc)}"
        )
        # Note: We don't raise here so typing indicator failures don't break
        # the message delivery pipeline. The retry decorator only retries
        # transient errors, not HTTPStatusError.

    except _TRANSIENT_ERRORS as exc:
        log.warning(f"Network warning setting typing indicator: {exc}")
        raise
