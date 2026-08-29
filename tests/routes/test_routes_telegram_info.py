"""Tests for telegram webhook info endpoint."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI
from src.routes.telegram import router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_telegram_info_endpoint(app):
    with patch("src.routes.telegram.get_telegram_webhook_info", new=AsyncMock(return_value={"url": "https://example.com"})), \
         patch("src.routes.telegram.get_telegram_me", new=AsyncMock(return_value={"username": "SamanthaBot"})), \
         patch("src.routes.telegram.get_simon_chat_id", new=AsyncMock(return_value="12345")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/telegram/info")
            assert resp.status_code == 200
            data = resp.json()
            assert data["simon_chat_id"] == "12345"
            assert data["bot_info"]["username"] == "SamanthaBot"
