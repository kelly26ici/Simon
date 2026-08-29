"""Tests for lifespan context manager in src/uptime.py."""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI
from src.uptime import lifespan


@pytest.mark.asyncio
async def test_lifespan_initializes_and_cleans_up():
    app = FastAPI()
    with patch("src.uptime.get_http_client") as mock_get_client, \
         patch("src.uptime.close_http_client", new=AsyncMock()) as mock_close_client, \
         patch("src.uptime._keep_alive", new=AsyncMock()), \
         patch("src.uptime._keep_databases_alive", new=AsyncMock()):
        
        async with lifespan(app):
            mock_get_client.assert_called()
        
        mock_close_client.assert_awaited_once()
