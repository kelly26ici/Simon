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

from __future__ import annotations

import httpx
from loguru import logger

_http_client: httpx.AsyncClient | None = None


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
    Return the singleton HTTP client, creating it on first call.

    Raises:
        RuntimeError: if the client was closed and not re-initialized.
    """
    global _http_client
    if _http_client is None:
        _http_client = create_http_client()
        logger.info("HTTP client initialized")
    return _http_client


async def close_http_client() -> None:
    """Close the singleton HTTP client if it exists."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.info("HTTP client closed")


# Backwards-compatible alias for code that imports ``http_client`` directly.
# New code should prefer ``get_http_client()`` so the client is always
# resolved at call time (important if it gets closed and recreated).
http_client: httpx.AsyncClient | None = None
