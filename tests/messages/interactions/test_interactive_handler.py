"""Tests for handle_interactive in src/messages/interactions/interactive_handler.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.messages.interactions.interactive_handler import handle_interactive


@pytest.mark.asyncio
async def test_handle_button_reply():
    msg = {
        "id": "msg_001",
        "interactive": {
            "type": "button_reply",
            "button_reply": {"id": "btn_yes", "title": "Yes, Book Viewing"}
        }
    }
    with patch("src.messages.interactions.interactive_handler.handle_text", new=AsyncMock()) as mock_text:
        await handle_interactive("254700000000", msg)
        mock_text.assert_awaited_once()
        _, synth_msg = mock_text.call_args[0]
        assert synth_msg["text"]["body"] == "Yes, Book Viewing"


@pytest.mark.asyncio
async def test_handle_list_reply():
    msg = {
        "id": "msg_002",
        "interactive": {
            "type": "list_reply",
            "list_reply": {"id": "prop_123", "title": "2 Bedroom in Kilimani"}
        }
    }
    with patch("src.messages.interactions.interactive_handler.handle_text", new=AsyncMock()) as mock_text:
        await handle_interactive("254700000000", msg)
        mock_text.assert_awaited_once()
        _, synth_msg = mock_text.call_args[0]
        assert synth_msg["text"]["body"] == "2 Bedroom in Kilimani"


@pytest.mark.asyncio
async def test_handle_nfm_flow_reply():
    msg = {
        "id": "msg_003",
        "interactive": {
            "type": "nfm_reply",
            "nfm_reply": {"response_json": '{"budget": 15000000}'}
        }
    }
    with patch("src.messages.interactions.interactive_handler.handle_text", new=AsyncMock()) as mock_text:
        await handle_interactive("254700000000", msg)
        mock_text.assert_awaited_once()
        _, synth_msg = mock_text.call_args[0]
        assert synth_msg["text"]["body"] == '{"budget": 15000000}'
