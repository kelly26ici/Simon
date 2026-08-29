"""Tests for transaction database methods in src/services/db.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.db import db


@pytest.mark.asyncio
async def test_create_mpesa_transaction_when_no_client():
    with patch.object(db, "client", None):
        await db.save_mpesa_transaction(
            checkout_request_id="ws_CO_12345",
            data={"amount": 50000, "phone_number": "254700000000"},
        )


@pytest.mark.asyncio
async def test_get_mpesa_transaction_when_no_client():
    with patch.object(db, "client", None):
        res = await db.get_mpesa_transaction("ws_CO_12345")
        assert res is None
