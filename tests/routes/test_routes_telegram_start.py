"""Tests for telegram webhook start/setup command."""

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
async def test_telegram_webhook_start_command(app):
    update_payload = {
        "message": {
            "chat": {"id": 987654321},
            "from": {"username": "simon_agent", "first_name": "Simon"},
            "text": "/start"
        }
    }
    with patch("src.routes.telegram.save_simon_chat_id", new=AsyncMock()) as mock_save, \
         patch("src.routes.telegram.send_telegram_message", new=AsyncMock()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/telegram/webhook", json=update_payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["action"] == "owner_registered"
            assert data["chat_id"] == 987654321
            mock_save.assert_awaited_once()
