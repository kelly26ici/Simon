"""Tests for property query database methods in src/services/db.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.db import db


@pytest.mark.asyncio
async def test_get_property_by_id_when_no_client():
    with patch.object(db, "client", None):
        res = await db.get_property_by_id("prop_123")
        assert res is None


@pytest.mark.asyncio
async def test_search_properties_when_no_client():
    with patch.object(db, "client", None):
        res = await db.search_properties(property_type="apartment")
        assert res == []
