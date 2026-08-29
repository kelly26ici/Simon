"""Tests for customer profile database methods in src/services/db.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.db import db


@pytest.mark.asyncio
async def test_get_customer_profile_when_no_client():
    with patch.object(db, "client", None):
        res = await db.get_customer_profile("254700000000")
        assert res is None


@pytest.mark.asyncio
async def test_upsert_customer_profile_when_no_client():
    with patch.object(db, "client", None):
        res = await db.upsert_customer_profile("254700000000", {"preferred_name": "Alice"})
        assert res is None


@pytest.mark.asyncio
async def test_get_customer_profile_success():
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_res = MagicMock()
    mock_res.data = [{"whatsapp_id": "254700000000", "preferred_name": "Bob"}]

    mock_eq.execute.return_value = mock_res
    mock_select.eq.return_value = mock_eq
    mock_table.select.return_value = mock_select

    mock_client = MagicMock()
    mock_client.table.return_value = mock_table

    with patch.object(db, "client", mock_client):
        res = await db.get_customer_profile("254700000000")
        assert res == {"whatsapp_id": "254700000000", "preferred_name": "Bob"}
