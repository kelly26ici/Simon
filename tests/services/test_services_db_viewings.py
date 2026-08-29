"""Tests for viewing scheduling database methods in src/services/db.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.db import db


@pytest.mark.asyncio
async def test_create_viewing_when_no_client():
    with patch.object(db, "client", None):
        res = await db.create_scheduled_viewing(
            customer_phone="254700000000",
            customer_name="Alice",
            property_id="prop_123",
            viewing_date="2026-09-01 10:00:00",
        )
        assert res["status"] == "error"


@pytest.mark.asyncio
async def test_get_customer_viewings_when_no_client():
    with patch.object(db, "client", None):
        res = await db.get_customer_viewings("254700000000")
        assert res == []
