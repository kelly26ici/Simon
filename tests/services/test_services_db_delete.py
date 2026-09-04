"""Tests for delete_property Qdrant sync in src/services/db.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.db import db


@pytest.mark.asyncio
async def test_delete_property_with_no_client():
    with patch.object(db, "client", None):
        res = await db.delete_property("prop_123")
        assert res is False


@pytest.mark.asyncio
async def test_delete_property_removes_from_both_db_and_qdrant():
    """Deleting a property should remove it from Supabase AND Qdrant."""
    mock_response = MagicMock()
    mock_response.data = [{"id": "prop-123"}]

    with patch.object(db, "client") as mock_client, \
         patch("src.tools.properties.delete_property_index", new=AsyncMock(return_value=True)) as mock_qdrant_delete:
        mock_table = MagicMock()
        mock_delete = MagicMock()
        mock_delete.eq = MagicMock(return_value=MagicMock(execute=MagicMock(return_value=mock_response)))
        mock_table.delete = MagicMock(return_value=mock_delete)
        mock_client.table = MagicMock(return_value=mock_table)

        result = await db.delete_property("prop-123")

        assert result is True
        mock_qdrant_delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_property_qdrant_failure_does_not_break_db_delete():
    """If Qdrant deletion fails, the Supabase deletion should still succeed."""
    mock_response = MagicMock()
    mock_response.data = [{"id": "prop-456"}]

    with patch.object(db, "client") as mock_client, \
         patch("src.tools.properties.delete_property_index", new=AsyncMock(side_effect=Exception("Qdrant down"))) as mock_qdrant_delete:
        mock_table = MagicMock()
        mock_delete = MagicMock()
        mock_delete.eq = MagicMock(return_value=MagicMock(execute=MagicMock(return_value=mock_response)))
        mock_table.delete = MagicMock(return_value=mock_delete)
        mock_client.table = MagicMock(return_value=mock_table)

        result = await db.delete_property("prop-456")

        # DB delete should still succeed
        assert result is True
        mock_qdrant_delete.assert_awaited_once()
