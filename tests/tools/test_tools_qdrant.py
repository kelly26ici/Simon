"""Tests for Qdrant client proxy and collections in src/tools/qdrant.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.qdrant import check_if_collection_exists, PROPERTIES_COLLECTION


@pytest.mark.asyncio
async def test_check_if_collection_exists_true():
    mock_col = MagicMock()
    mock_col.name = PROPERTIES_COLLECTION
    mock_resp = MagicMock()
    mock_resp.collections = [mock_col]

    with patch("src.tools.qdrant.client.get_collections", new=AsyncMock(return_value=mock_resp)):
        exists = await check_if_collection_exists(PROPERTIES_COLLECTION)
        assert exists is True


@pytest.mark.asyncio
async def test_check_if_collection_exists_false():
    mock_resp = MagicMock()
    mock_resp.collections = []

    with patch("src.tools.qdrant.client.get_collections", new=AsyncMock(return_value=mock_resp)):
        exists = await check_if_collection_exists(PROPERTIES_COLLECTION)
        assert exists is False
