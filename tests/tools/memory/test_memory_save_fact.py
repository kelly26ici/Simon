"""Tests for save_customer_fact tool in src/tools/memory/tools.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.tools.memory.tools import save_customer_fact
from src.tools.memory.schemas import SaveCustomerFactSchema


@pytest.mark.asyncio
async def test_save_customer_fact_calls_db():
    payload = SaveCustomerFactSchema(
        phone_number="254700000000",
        field="preferred_name",
        value="Brian",
    )
    with patch("src.tools.memory.tools.db.upsert_customer_profile", new=AsyncMock()) as mock_upsert:
        res = await save_customer_fact(payload)
        assert res["status"] == "success"
        mock_upsert.assert_awaited_once_with("254700000000", {"preferred_name": "Brian"})
