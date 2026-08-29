"""Tests for handle_text() in src/messages/chats/text_handler.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.messages.chats.text_handler import handle_text


@pytest.mark.asyncio
async def test_handle_text_successful_response():
    sender = "254700000000"
    msg = {"id": "wamid.123", "text": {"body": "Looking for apartments"}}

    mock_llm_resp = MagicMock()
    mock_llm_resp.output_text = "Here are some apartments"

    with patch("src.messages.chats.text_handler.send_typing_indicator", new=AsyncMock()), \
         patch("src.messages.chats.text_handler.get_history", new=AsyncMock(return_value=[])), \
         patch("src.messages.chats.text_handler.append_message", new=AsyncMock()), \
         patch("src.messages.chats.text_handler._build_customer_context_string", new=AsyncMock(return_value="")), \
         patch("src.messages.chats.text_handler.ask_llm", new=AsyncMock(return_value=mock_llm_resp)), \
         patch("src.messages.chats.text_handler.db.save_message", new=AsyncMock()), \
         patch("src.messages.chats.text_handler.send_whatsapp_message", new=AsyncMock()) as mock_send:
        
        await handle_text(sender, msg)
        mock_send.assert_awaited_once_with(sender, "Here are some apartments", phone_number_id=None)
