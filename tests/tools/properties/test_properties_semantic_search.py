"""Tests for semantic_search_properties tool in src/tools/properties/tools.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.tools.properties.tools import semantic_search_properties
from src.tools.properties.schemas import SemanticSearchSchema


@pytest.mark.asyncio
async def test_semantic_search_properties_returns_results():
    payload = SemanticSearchSchema(query="Serene family villa with pool in Karen")
    fake_semantic_results = [
        {"id": "prop_v1", "title": "Karen Sanctuary Villa", "price": 45000000, "score": 0.89}
    ]
    with patch("src.tools.properties.tools.semantic_search", new=AsyncMock(return_value=fake_semantic_results)):
        res = await semantic_search_properties(payload)
        assert res["total"] == 1
        assert res["results"][0]["id"] == "prop_v1"
