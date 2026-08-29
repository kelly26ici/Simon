"""Tests for get_http_client() and close_http_client() in src/clients/httpx_client.py."""

import asyncio
import pytest
import httpx
import src.clients.httpx_client as httpx_module


@pytest.mark.asyncio
async def test_get_http_client_returns_async_client():
    client = httpx_module.get_http_client()
    assert isinstance(client, httpx.AsyncClient)


@pytest.mark.asyncio
async def test_get_http_client_same_instance_per_loop():
    """Calling get_http_client twice in same loop should return the same object."""
    c1 = httpx_module.get_http_client()
    c2 = httpx_module.get_http_client()
    assert c1 is c2


@pytest.mark.asyncio
async def test_close_http_client_closes_client():
    client = httpx_module.get_http_client()
    assert not client.is_closed
    await httpx_module.close_http_client()
    assert client.is_closed


@pytest.mark.asyncio
async def test_get_http_client_recreates_after_close():
    await httpx_module.close_http_client()
    client = httpx_module.get_http_client()
    assert isinstance(client, httpx.AsyncClient)
    assert not client.is_closed
    # Cleanup
    await httpx_module.close_http_client()
