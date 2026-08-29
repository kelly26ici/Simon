"""Tests for get_history() and append_message() in src/messages/chats/conversation.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.messages.chats.conversation import get_history, append_message

PHONE = "254700000001"


@pytest.mark.asyncio
async def test_get_history_returns_list():
    with patch("src.messages.chats.conversation._conversations.get", new=AsyncMock(return_value=[])):
        history = await get_history(PHONE)
        assert isinstance(history, list)


@pytest.mark.asyncio
async def test_get_history_empty_when_no_stored_data():
    with patch("src.messages.chats.conversation._conversations.get", new=AsyncMock(return_value=None)), \
         patch("src.messages.chats.conversation._conversations.set", new=AsyncMock()):
        history = await get_history(PHONE)
        assert history == []


@pytest.mark.asyncio
async def test_append_message_stores_data():
    with patch("src.messages.chats.conversation._conversations.get", new=AsyncMock(return_value=[])), \
         patch("src.messages.chats.conversation._conversations.set", new=AsyncMock()) as mock_set:
        await append_message(PHONE, "user", "Hello there")
        mock_set.assert_awaited()
