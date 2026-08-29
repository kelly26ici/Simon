"""Tests for update_conversation_summary tool in src/tools/memory/tools.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.tools.memory.tools import update_conversation_summary
from src.tools.memory.schemas import UpdateConversationSummarySchema


@pytest.mark.asyncio
async def test_update_conversation_summary_success():
    payload = UpdateConversationSummarySchema(
        phone_number="254700000000",
        summary="Customer interested in Karen properties under 50M KES",
    )
    with patch("src.tools.memory.tools.db.upsert_conversation_summary", new=AsyncMock(return_value=True)):
        res = await update_conversation_summary(payload)
        assert res["status"] == "success"
