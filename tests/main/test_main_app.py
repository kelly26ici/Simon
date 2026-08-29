"""Tests for main FastAPI application in src/main.py."""

import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app


@pytest.mark.asyncio
async def test_app_title_and_version():
    assert app.title == "Realtors Round Tables API"
    assert app.version == "1.0.0"


@pytest.mark.asyncio
async def test_app_uptime_route():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/uptime")
        assert resp.status_code == 200
        data = resp.json()
        assert "Simon" in data["uptime"]
