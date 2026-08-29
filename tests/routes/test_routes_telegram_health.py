"""Tests for telegram webhook healthcheck endpoint."""

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
async def test_telegram_webhook_health(app):
    with patch("src.routes.telegram.get_simon_chat_id", new=AsyncMock(return_value="12345678")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/telegram/webhook")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "active"
            assert data["simon_chat_id_configured"] is True
