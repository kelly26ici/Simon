# src/clients/httpx_client.py
"""
Shared HTTP client singleton with retry transport and proper lifecycle management.

The client is created lazily on first access via ``get_http_client()`` and must
be closed during application shutdown via ``close_http_client()`` to avoid
resource leaks (unclosed connections, sockets, etc.).

Usage in request handlers:
    client = get_http_client()
    resp = await client.get(url)

Usage in lifespan:
    # startup
    client = get_http_client()
    # shutdown
    await close_http_client()
"""

import asyncio
import httpx
from loguru import logger

_http_clients_by_loop: dict[asyncio.AbstractEventLoop | None, httpx.AsyncClient] = {}


def create_http_client() -> httpx.AsyncClient:
    """Create a new ``AsyncClient`` with retry transport and sensible defaults."""
    transport = httpx.AsyncHTTPTransport(retries=3)
    return httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
        transport=transport,
    )


def get_http_client() -> httpx.AsyncClient:
    """
    Return the event-loop scoped HTTP client, creating it if needed.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    client = _http_clients_by_loop.get(loop)
    if client is None or client.is_closed:
        client = create_http_client()
        _http_clients_by_loop[loop] = client
        logger.info("HTTP client initialized")
    return client


async def close_http_client() -> None:
    """Close the HTTP client for the current event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    client = _http_clients_by_loop.pop(loop, None)
    if client is not None and not client.is_closed:
        await client.aclose()
        logger.info("HTTP client closed")


http_client: httpx.AsyncClient | None = None
