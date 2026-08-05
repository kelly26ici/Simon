import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.clients.httpx_client import get_http_client, close_http_client
from src.configs.settings import RENDER_BASE_URL


async def _keep_alive():
    """Periodically ping the base URL to prevent the service from going idle."""
    await asyncio.sleep(10)

    while True:
        try:
            client = get_http_client()
            response = await client.get(RENDER_BASE_URL, timeout=10.0)
            logger.info("Keep-alive ping successful: Status {}", response.status_code)
        except asyncio.CancelledError:
            logger.info("Keep-alive task stopped.")
            break
        except Exception:
            logger.exception("Error pinging uptime endpoint")

        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure the HTTP client is initialized before serving requests
    get_http_client()
    keep_alive_task = asyncio.create_task(_keep_alive())
    try:
        yield
    finally:
        keep_alive_task.cancel()
        try:
            await keep_alive_task
        except asyncio.CancelledError:
            pass
        await close_http_client()
