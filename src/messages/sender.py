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


def _get_messages_url(phone_number_id: str | None = None) -> str:
    """Constructs the base WhatsApp messages endpoint."""
    pid = (phone_number_id or "").strip() or META_PHONE_NUMBER_ID
    return f"{META_GRAPH_BASE_URL}/{META_GRAPH_API_VERSION}/{pid}/messages"


def _extract_error_details(exc: httpx.HTTPStatusError) -> dict:
    """Extracts Meta's rich JSON error response from an HTTPStatusError."""
    try:
        return exc.response.json().get("error", {})
    except Exception:
        return {"raw": exc.response.text}


async def _send_single_message(to: str, text: str, phone_number_id: str | None = None) -> str | None:
    """Sends a single WhatsApp text message (no formatting, no splitting).

    Returns the Meta message ID on success, or None on failure.
    """
    url = _get_messages_url(phone_number_id)
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


async def send_whatsapp_message(to: str, text: str, phone_number_id: str | None = None) -> None:
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
        await _send_single_message(to, msg, phone_number_id=phone_number_id)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(_TRANSIENT_ERRORS),
    before_sleep=before_sleep_log(logger, "WARNING"),
)
async def send_typing_indicator(message_id: str, phone_number_id: str | None = None) -> None:
    """Marks the inbound message as read and displays the typing bubble."""
    url = _get_messages_url(phone_number_id)
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


async def send_whatsapp_interactive_cta(
    to: str,
    body_text: str,
    button_text: str,
    url: str,
    header_text: str | None = None,
    footer_text: str | None = None,
    phone_number_id: str | None = None,
) -> str | None:
    """
    Sends a WhatsApp interactive Call-To-Action (CTA) URL button.
    Tapping the button immediately opens the URL (e.g. WhatsApp direct link or website).
    """
    url_endpoint = _get_messages_url(phone_number_id)
    interactive_payload: dict = {
        "type": "cta_url",
        "body": {"text": body_text},
        "action": {
            "name": "cta_url",
            "parameters": {
                "display_text": button_text[:20],
                "url": url,
            },
        },
    }

    if header_text:
        interactive_payload["header"] = {"type": "text", "text": header_text}
    if footer_text:
        interactive_payload["footer"] = {"text": footer_text[:60]}

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": interactive_payload,
    }

    log = logger.bind(recipient=to, action="send_whatsapp_interactive_cta")

    try:
        client = get_http_client()
        resp = await client.post(url_endpoint, headers=_get_headers(), json=payload)
        resp.raise_for_status()

        data = resp.json()
        meta_msg_id = data.get("messages", [{}])[0].get("id")
        log.bind(wa_mid=meta_msg_id).info("WhatsApp CTA interactive message sent successfully")
        return meta_msg_id
    except Exception as exc:
        log.error("Failed to send WhatsApp CTA interactive message: {}", exc)
        # Fallback to standard text message if interactive fails
        fallback_text = f"{body_text}\n\n👉 {button_text}: {url}"
        await send_whatsapp_message(to, fallback_text, phone_number_id=phone_number_id)
        return None


async def send_whatsapp_quick_replies(
    to: str,
    body_text: str,
    buttons: list[dict[str, str]],
    header_text: str | None = None,
    footer_text: str | None = None,
    phone_number_id: str | None = None,
) -> str | None:
    """
    Sends a WhatsApp interactive message with up to 3 quick reply buttons.
    """
    url_endpoint = _get_messages_url(phone_number_id)
    formatted_buttons = [
        {
            "type": "reply",
            "reply": {
                "id": btn.get("id", f"btn_{i}"),
                "title": btn.get("title", "")[:20],
            },
        }
        for i, btn in enumerate(buttons[:3])
    ]

    interactive_payload: dict = {
        "type": "button",
        "body": {"text": body_text},
        "action": {
            "buttons": formatted_buttons,
        },
    }

    if header_text:
        interactive_payload["header"] = {"type": "text", "text": header_text}
    if footer_text:
        interactive_payload["footer"] = {"text": footer_text[:60]}

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": interactive_payload,
    }

    log = logger.bind(recipient=to, action="send_whatsapp_quick_replies")

    try:
        client = get_http_client()
        resp = await client.post(url_endpoint, headers=_get_headers(), json=payload)
        resp.raise_for_status()

        data = resp.json()
        meta_msg_id = data.get("messages", [{}])[0].get("id")
        log.bind(wa_mid=meta_msg_id).info("WhatsApp quick replies interactive message sent")
        return meta_msg_id
    except Exception as exc:
        log.error("Failed to send WhatsApp quick replies: {}", exc)
        fallback_text = f"{body_text}\n" + "\n".join(f"• {b.get('title')}" for b in buttons)
        await send_whatsapp_message(to, fallback_text, phone_number_id=phone_number_id)
        return None

