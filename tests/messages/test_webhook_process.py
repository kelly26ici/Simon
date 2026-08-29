"""Tests for process_webhook_event() in src/messages/webhook.py."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


VALID_PAYLOAD = json.dumps({
    "entry": [{
        "changes": [{
            "value": {
                "metadata": {"phone_number_id": "123"},
                "messages": [{
                    "from": "254700000000",
                    "type": "text",
                    "id": "msg-001",
                    "text": {"body": "Hello"}
                }]
            }
        }]
    }]
}).encode()


def _make_valid_sig(payload: bytes, secret: str) -> str:
    import hmac, hashlib
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.mark.asyncio
async def test_invalid_signature_returns_403():
    from src.messages.webhook import process_webhook_event
    with patch("src.messages.webhook.verify_signature", return_value=False):
        resp = await process_webhook_event(VALID_PAYLOAD, "sha256=bad")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_status_update_returns_200():
    status_payload = json.dumps({
        "entry": [{"changes": [{"value": {"statuses": [{"id": "abc"}]}}]}]
    }).encode()
    from src.messages.webhook import process_webhook_event
    with patch("src.messages.webhook.verify_signature", return_value=True):
        resp = await process_webhook_event(status_payload, "sha256=valid")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_valid_message_dispatched_returns_200():
    from src.messages.webhook import process_webhook_event
    with patch("src.messages.webhook.verify_signature", return_value=True), \
         patch("src.messages.webhook.dispatch", new=AsyncMock()), \
         patch("src.messages.webhook.SeenMessages.get", new=AsyncMock(return_value=None)), \
         patch("src.messages.webhook.SeenMessages.set", new=AsyncMock()):
        resp = await process_webhook_event(VALID_PAYLOAD, "sha256=valid")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_duplicate_message_skipped():
    from src.messages.webhook import process_webhook_event
    dispatch_mock = AsyncMock()
    with patch("src.messages.webhook.verify_signature", return_value=True), \
         patch("src.messages.webhook.dispatch", new=dispatch_mock), \
         patch("src.messages.webhook.SeenMessages.get", new=AsyncMock(return_value="1")), \
         patch("src.messages.webhook.SeenMessages.set", new=AsyncMock()):
        resp = await process_webhook_event(VALID_PAYLOAD, "sha256=valid")
    dispatch_mock.assert_not_called()
    assert resp.status_code == 200
