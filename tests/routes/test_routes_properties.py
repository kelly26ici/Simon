"""Tests for property CRUD API routes in src/routes/properties.py."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.security import HTTPBasicCredentials
from src.routes.properties import router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_search_properties_api_returns_results(app):
    fake_props = [
        {"id": "p1", "title": "Apartment 1", "price": 10000000, "property_type": "apartment"},
        {"id": "p2", "title": "Apartment 2", "price": 12000000, "property_type": "apartment"},
    ]
    with patch("src.routes.properties.db.search_properties_advanced", new=AsyncMock(return_value=fake_props)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/properties/?location=Westlands&limit=5")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 2
            assert len(data["results"]) == 2
            assert data["results"][0]["title"] == "Apartment 1"


@pytest.mark.asyncio
async def test_search_properties_api_no_results(app):
    with patch("src.routes.properties.db.search_properties_advanced", new=AsyncMock(return_value=[])):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/properties/?location=Nowhere")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 0
            assert data["results"] == []


@pytest.mark.asyncio
async def test_get_property_by_id_found(app):
    fake_prop = {"id": "p-123", "title": "Luxury Villa", "price": 50000000}
    with patch("src.routes.properties.db.get_property_by_id", new=AsyncMock(return_value=fake_prop)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/properties/p-123")
            assert resp.status_code == 200
            assert resp.json()["title"] == "Luxury Villa"


@pytest.mark.asyncio
async def test_get_property_by_id_not_found(app):
    with patch("src.routes.properties.db.get_property_by_id", new=AsyncMock(return_value=None)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/properties/nonexistent")
            assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_property_requires_auth(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "title": "New Property",
            "description": "A nice property",
            "property_type": "apartment",
            "listing_type": "sale",
            "price": 15000000,
            "location": "Kilimani",
        }
        resp = await client.post("/api/properties/", json=payload)
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_property_with_auth(app):
    fake_result = {"id": "new-uuid", "title": "New Property"}
    with patch("src.routes.properties.db.upsert_property", new=AsyncMock(return_value=fake_result)), \
         patch("src.routes.properties.index_property", new=AsyncMock(return_value=True)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "title": "New Property",
                "description": "A nice property description",
                "property_type": "apartment",
                "listing_type": "sale",
                "price": 15000000,
                "location": "Kilimani",
            }
            resp = await client.post(
                "/api/properties/",
                json=payload,
                headers={"Authorization": "Basic " + __import__("base64").b64encode(b"admin:changeme").decode()},
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["id"] == "new-uuid"
            assert data["status"] == "created"


@pytest.mark.asyncio
async def test_delete_property_requires_auth(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/api/properties/some-id")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_property_with_auth(app):
    with patch("src.routes.properties.db.delete_property", new=AsyncMock(return_value=True)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete(
                "/api/properties/prop-123",
                headers={"Authorization": "Basic " + __import__("base64").b64encode(b"admin:changeme").decode()},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "deleted"


@pytest.mark.asyncio
async def test_delete_property_not_found(app):
    with patch("src.routes.properties.db.delete_property", new=AsyncMock(return_value=False)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete(
                "/api/properties/nonexistent",
                headers={"Authorization": "Basic " + __import__("base64").b64encode(b"admin:changeme").decode()},
            )
            assert resp.status_code == 404
