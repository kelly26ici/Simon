"""Tests for _build_customer_context_string in src/messages/chats/text_handler.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.messages.chats.text_handler import _build_customer_context_string


@pytest.mark.asyncio
async def test_build_context_with_empty_profile():
    with patch("src.messages.chats.text_handler.db.get_customer_profile", new=AsyncMock(return_value=None)), \
         patch("src.messages.chats.text_handler.db.get_customer_viewings", new=AsyncMock(return_value=[])):
        ctx = await _build_customer_context_string("254700000000")
        assert "Customer WhatsApp ID / Phone: 254700000000" in ctx


@pytest.mark.asyncio
async def test_build_context_with_populated_profile():
    fake_profile = {
        "preferred_name": "Alice",
        "budget_range": "10M - 15M KES",
        "preferred_area": "Kilimani",
        "metadata": {"bedrooms": 3}
    }
    with patch("src.messages.chats.text_handler.db.get_customer_profile", new=AsyncMock(return_value=fake_profile)), \
         patch("src.messages.chats.text_handler.db.get_customer_viewings", new=AsyncMock(return_value=[])):
        ctx = await _build_customer_context_string("254700000000")
        assert "Customer Name: Alice" in ctx
        assert "Known Budget: 10M - 15M KES" in ctx
        assert "Preferred Neighborhood: Kilimani" in ctx
