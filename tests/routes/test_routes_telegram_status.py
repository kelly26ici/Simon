"""Tests for telegram webhook status command."""

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
async def test_telegram_webhook_status_command(app):
    update_payload = {
        "message": {
            "chat": {"id": 987654321},
            "from": {"username": "simon_agent", "first_name": "Simon"},
            "text": "/status"
        }
    }
    with patch("src.routes.telegram.get_simon_chat_id", new=AsyncMock(return_value="987654321")), \
         patch("src.routes.telegram.send_telegram_message", new=AsyncMock()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/telegram/webhook", json=update_payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["action"] == "status_sent"
