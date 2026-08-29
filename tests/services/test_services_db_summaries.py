"""Tests for conversation summary database methods in src/services/db.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.db import db


@pytest.mark.asyncio
async def test_get_conversation_summary_when_no_client():
    with patch.object(db, "client", None):
        res = await db.get_conversation_summary("254700000000")
        assert res is None


@pytest.mark.asyncio
async def test_upsert_conversation_summary_fallback_returns_true():
    with patch.object(db, "client", None), \
         patch.object(db, "upsert_customer_profile", new=AsyncMock()):
        res = await db.upsert_conversation_summary("254700000000", "Summary of conversation")
        assert res is True
