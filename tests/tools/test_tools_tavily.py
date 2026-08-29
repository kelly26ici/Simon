"""Tests for web_search tool in src/tools/tavily.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.tavily import web_search, TavilySearchSchema


@pytest.mark.asyncio
async def test_web_search_no_api_key():
    with patch("src.tools.tavily.TAVILY_API_KEY", ""):
        payload = TavilySearchSchema(query="Real estate prices Nairobi 2026")
        res = await web_search(payload)
        assert "error" in res
        assert "unavailable" in res["error"]


@pytest.mark.asyncio
async def test_web_search_success():
    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value={"results": [{"title": "Nairobi Market Report", "url": "https://example.com"}]})

    with patch("src.tools.tavily.TAVILY_API_KEY", "tvly-test-123"), \
         patch("src.tools.tavily._get_tavily_client", return_value=mock_client):
        payload = TavilySearchSchema(query="Nairobi property tax 2026")
        res = await web_search(payload)
        assert "results" in res
        assert len(res["results"]) == 1
