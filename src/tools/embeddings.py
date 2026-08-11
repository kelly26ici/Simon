import os
from typing import List

import httpx
from loguru import logger

from src.clients.httpx_client import get_http_client

CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_API_URL = (
    f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}"
    "/ai/run/@cf/qwen/qwen3-embedding-0.6b"
)


async def get_embeddings(text_chunks: list[str]) -> List[List[float]]:
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        raise ValueError(
            "CLOUDFLARE_ACCOUNT_ID and/or CLOUDFLARE_API_TOKEN "
            "missing in environment variables"
        )

    if not text_chunks:
        raise ValueError(
            "get_embeddings() receives text chunks as a list of strings. "
            "Text chunks cannot be empty"
        )

    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"text": text_chunks}

    try:
        client = get_http_client()
        response = await client.post(
            CLOUDFLARE_API_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Cloudflare embeddings HTTP error [{}]: {}",
            getattr(exc.response, "status_code", None),
            exc,
        )
        return []
    except httpx.TimeoutException as exc:
        logger.error("Cloudflare embeddings request timed out: {}", exc)
        return []
    except httpx.RequestError as exc:
        logger.error("Network error calling Cloudflare embeddings: {}", exc)
        return []
    except Exception as exc:
        logger.exception("Unexpected error fetching embeddings")
        return []

    try:
        data = response.json()
    except Exception as exc:
        logger.exception("Failed to decode embeddings response: {}", exc)
        return []

    try:
        return data["result"]["data"]
    except Exception as exc:
        logger.exception("Embeddings response missing expected schema: {}", exc)
        return []
