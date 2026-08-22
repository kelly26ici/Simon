import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from scripts.keep_alive import ping_qdrant, ping_supabase
from src.clients.httpx_client import close_http_client, get_http_client
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
        except Exception as exc:
            logger.exception("Error pinging uptime endpoint: {}", exc)

        await asyncio.sleep(300)


async def _keep_databases_alive():
    """Periodically ping Supabase and Qdrant databases every 6 hours to prevent free-tier pausing."""
    await asyncio.sleep(15)

    while True:
        try:
            sb_ok = await asyncio.to_thread(ping_supabase)
            qd_ok = await asyncio.to_thread(ping_qdrant)

            if sb_ok:
                logger.info("Supabase database keep-alive ping successful.")
            else:
                logger.warning("Supabase database keep-alive ping returned failure.")

            if qd_ok:
                logger.info("Qdrant cluster keep-alive ping successful.")
            else:
                logger.warning("Qdrant cluster keep-alive ping returned failure.")
        except asyncio.CancelledError:
            logger.info("Database keep-alive task stopped.")
            break
        except Exception as exc:
            logger.exception("Error during database keep-alive task: {}", exc)

        # Ping every 6 hours (21,600 seconds)
        await asyncio.sleep(21600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure the HTTP client is initialized before serving requests
    get_http_client()
    keep_alive_task = asyncio.create_task(_keep_alive())
    db_keep_alive_task = asyncio.create_task(_keep_databases_alive())
    try:
        yield
    finally:
        keep_alive_task.cancel()
        db_keep_alive_task.cancel()
        try:
            await asyncio.gather(
                keep_alive_task, db_keep_alive_task, return_exceptions=True
            )
        except Exception:
            pass
        await close_http_client()
