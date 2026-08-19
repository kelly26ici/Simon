import os
import asyncio
from typing import List

import httpx
from loguru import logger

from src.clients.httpx_client import get_http_client
from src.configs.settings import (
    OPENROUTER_API_KEY,
)

CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_API_URL = (
    f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}"
    "/ai/run/@cf/qwen/qwen3-embedding-0.6b"
) if CLOUDFLARE_ACCOUNT_ID else ""

BATCH_SIZE = 20  # Cloudflare free-tier per-request limit


async def _embed_batch_cloudflare(batch: list[str]) -> List[List[float]]:
    """Embed a single batch of up to 20 texts via Cloudflare Workers AI."""
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        raise ValueError("Cloudflare credentials missing")

    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"text": batch}

    client = get_http_client()
    response = await client.post(
        CLOUDFLARE_API_URL,
        headers=headers,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data["result"]["data"]


async def get_embeddings(text_chunks: list[str]) -> List[List[float]]:
    """Generates 1024-dimensional embeddings for a list of strings with auto-batching."""
    if not text_chunks:
        return []

    # Clean text chunks
    cleaned = [t.strip() for t in text_chunks if t and t.strip()]
    if not cleaned:
        return []

    all_embeddings: List[List[float]] = []

    # 1. Try Cloudflare Workers AI with batching
    if CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN:
        try:
            for i in range(0, len(cleaned), BATCH_SIZE):
                batch = cleaned[i : i + BATCH_SIZE]
                batch_embeddings = await _embed_batch_cloudflare(batch)
                all_embeddings.extend(batch_embeddings)
            return all_embeddings
        except Exception as exc:
            logger.warning("Cloudflare embeddings failed: {}. Checking fallbacks...", exc)

    logger.error("No embedding backend succeeded for {} text chunks", len(text_chunks))
    return []

