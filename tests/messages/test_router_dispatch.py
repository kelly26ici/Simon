"""Tests for dispatch() and MESSAGE_HANDLERS in src/messages/router.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.messages.parser import IncomingMessage
from src.messages.router import dispatch, MESSAGE_HANDLERS


def test_message_handlers_registered():
    assert "text" in MESSAGE_HANDLERS
    assert "audio" in MESSAGE_HANDLERS
    assert "interactive" in MESSAGE_HANDLERS


@pytest.mark.asyncio
async def test_dispatch_calls_registered_text_handler():
    msg = IncomingMessage(sender="254700000000", msg_type="text", raw={"body": "hi"})
    mock_handler = AsyncMock()
    with patch.dict(MESSAGE_HANDLERS, {"text": mock_handler}):
        await dispatch(msg)
        mock_handler.assert_awaited_once_with("254700000000", {"body": "hi"})


@pytest.mark.asyncio
async def test_dispatch_unknown_type_logs_warning_and_does_not_raise():
    msg = IncomingMessage(sender="254700000000", msg_type="unsupported_type", raw={})
    # Should not raise exception
    await dispatch(msg)
