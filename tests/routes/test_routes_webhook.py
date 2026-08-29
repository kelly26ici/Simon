"""Tests for webhook endpoints in src/routes/webhook.py."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI
from src.routes.webhook import router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_get_webhook_verification_success(app):
    with patch("src.routes.webhook.META_VERIFY_TOKEN", "secret_token"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/webhook", params={
                "hub.mode": "subscribe",
                "hub.verify_token": "secret_token",
                "hub.challenge": "1158201444"
            })
            assert resp.status_code == 200
            assert resp.text == "1158201444"


@pytest.mark.asyncio
async def test_get_webhook_verification_failure_wrong_token(app):
    with patch("src.routes.webhook.META_VERIFY_TOKEN", "secret_token"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/webhook", params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "1158201444"
            })
            assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_webhook_message_routes_to_process(app):
    with patch("src.routes.webhook.process_webhook_event", new=AsyncMock(return_value=pytest.importorskip("fastapi").Response(status_code=200))):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/webhook", content=b'{"object":"whatsapp"}', headers={"X-Hub-Signature-256": "sha256=123"})
            assert resp.status_code == 200
