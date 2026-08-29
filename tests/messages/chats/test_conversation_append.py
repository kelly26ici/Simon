"""Tests for append_interaction_steps() in src/messages/chats/conversation.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pydantic import BaseModel


class FakeStep(BaseModel):
    call_id: str
    name: str


@pytest.mark.asyncio
async def test_append_interaction_steps_with_pydantic():
    stored = {}
    mock_store = MagicMock()
    mock_store.get = AsyncMock(return_value=[])

    async def fake_set(key, value, ex=None):
        stored[key] = value

    mock_store.set = fake_set

    with patch("src.messages.chats.conversation._conversations", mock_store):
        from src.messages.chats.conversation import append_interaction_steps
        step = FakeStep(call_id="call_1", name="search_properties")
        await append_interaction_steps("254700000000", [step])

    assert "254700000000" in stored
    assert len(stored["254700000000"]) == 1
    assert stored["254700000000"][0] == {"call_id": "call_1", "name": "search_properties"}
