# src/messages/downloader.py

"""WhatsApp Cloud API media downloader.

Optimised with:
- Atomic two-step download wrapped in a single try/except so the caller
  does not need to handle partial-success states.
- Explicit handling for every httpx status / transport class.
- Returns a specific error tag alongside bytes so callers can react
  differently to "404 not found" vs "network down" vs "invalid token".
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from loguru import logger

from src.clients.httpx_client import get_http_client
from src.configs.settings import (
    META_ACCESS_TOKEN,
    META_GRAPH_API_VERSION,
    META_GRAPH_BASE_URL,
    META_PHONE_NUMBER_ID,
)

import httpx


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class MediaError(str, Enum):
    """Explanation: Enumerated failure modes so the caller can distinguish
    between "the file does not exist on Meta's servers" (404), "the app
    token is wrong or expired" (401/403), and "there is a network problem"
    (transport errors)."""

    INVALID_MEDIA_ID = "invalid_media_id"       # 400 / 404 in step-1
    AUTH_FAILED     = "auth_failed"              # 401 / 403 in either step
    RATE_LIMITED    = "rate_limited"             # 429
    DOWNLOAD_FAILED = "download_failed"          # other non-2xx in step-2
    TRANSPORT_ERROR = "transport_error"          # ConnectError, Timeout, etc.
    EMPTY_BODY      = "empty_body"               # 2xx but 0 bytes


@dataclass(frozen=True)
class MediaResult:
    """Immutable result of a download attempt."""

    data: Optional[bytes]
    error: Optional[MediaError]

    @property
    def ok(self) -> bool:
        return self.data is not None and self.error is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}


def _media_url(media_id: str) -> str:
    return (
        f"{META_GRAPH_BASE_URL}/{META_GRAPH_API_VERSION}/"
        f"{META_PHONE_NUMBER_ID}/media/{media_id}"
    )


# ---------------------------------------------------------------------------
# Core download — step 1: resolve media_id → temporary URL
# ---------------------------------------------------------------------------

async def _resolve_media_url(media_id: str, client: httpx.AsyncClient) -> tuple[Optional[str], Optional[MediaError]]:
    """Step 1 of the two-step Cloud API flow.

    Returns (url, error).  ``url`` is None when ``error`` is set.
    """
    url = _media_url(media_id)
    try:
        resp = await client.get(url, headers=_headers(), timeout=10)
    except httpx.TimeoutException as exc:
        logger.warning("Timeout resolving media {}: {}", media_id, exc)
        return None, MediaError.TRANSPORT_ERROR
    except httpx.NetworkError as exc:
        # Explanation: Covers ConnectError, ReadError, WriteError, etc.
        logger.warning("Network error resolving media {}: {}", media_id, exc)
        return None, MediaError.TRANSPORT_ERROR
    except httpx.HTTPStatusError as exc:
        # Explanation: 4xx/5xx raised by raise_for_status() — none of those
        # are triggered here because we handle status manually below instead.
        logger.error("HTTP error resolving media {}: {}", media_id, exc)
        return None, MediaError.TRANSPORT_ERROR
    except Exception as exc:
        # Explanation: Catch-all for truly unexpected cases (cancelled task,
        # programming errors) — these are logged with full traceback info.
        logger.exception("Unexpected error resolving media {}: {}", media_id, exc)
        return None, MediaError.TRANSPORT_ERROR

    status_raw = resp.status_code
    try:
        status: int = int(status_raw)
    except (TypeError, ValueError):
        logger.error(
            "Invalid HTTP status value '{}' resolving media {}",
            status_raw, media_id,
        )
        return None, MediaError.TRANSPORT_ERROR

    if status in (401, 403):
        logger.error(
            "Authentication failed resolving {} — check META_ACCESS_TOKEN (HTTP {})",
            media_id, status,
        )
        return None, MediaError.AUTH_FAILED

    if status in (400, 404):
        logger.warning("Media {} not on Meta's servers (HTTP {})", media_id, status)
        return None, MediaError.INVALID_MEDIA_ID

    if status == 429:
        retry_after = resp.headers.get("retry-after", "1")
        logger.warning(
            "Rate-limited resolving {} (HTTP 429, retry-after={})",
            media_id, retry_after,
        )
        return None, MediaError.RATE_LIMITED

    if status == 410:
        # Explanation: Meta returns 410 when the 5-minute media URL TTL
        # expired before we fetched it.
        logger.error("Media {} has expired (HTTP 410 Gone)", media_id)
        return None, MediaError.INVALID_MEDIA_ID

    if not (200 <= status < 300):
        logger.error("Unexpected HTTP {} resolving media {}", status, media_id)
        return None, MediaError.DOWNLOAD_FAILED

    content_type: str = resp.headers.get("content-type", "")
    remote_url: Optional[str] = None
    if content_type.startswith("application/json"):
        try:
            remote_url = resp.json().get("url")
        except Exception as exc:
            logger.warning(
                "Failed to parse JSON from step-1 response for {}: [{}] {}",
                media_id, type(exc).__qualname__, exc,
            )
    if not remote_url:
        logger.error(
            "Cloud API response for {} missing 'url' (HTTP {}, type={}, body={})",
            media_id, status, content_type,
            getattr(resp, "text", "")[:200],
        )
        return None, MediaError.DOWNLOAD_FAILED

    return remote_url, None


# ---------------------------------------------------------------------------
# Core download — step 2: fetch bytes from the temporary URL
# ---------------------------------------------------------------------------

async def _fetch_audio_bytes(remote_url: str, client: httpx.AsyncClient) -> tuple[Optional[bytes], Optional[MediaError]]:
    """Step 2 — download raw audio bytes from the resolved temporary URL."""
    try:
        resp = await client.get(remote_url, headers=_headers(), timeout=60)
    except httpx.TimeoutException as exc:
        logger.warning("Timeout downloading audio bytes: {}", exc)
        return None, MediaError.TRANSPORT_ERROR
    except httpx.NetworkError as exc:
        logger.warning("Network error downloading audio bytes: {}", exc)
        return None, MediaError.TRANSPORT_ERROR
    except httpx.HTTPStatusError as exc:
        logger.error("HTTP error downloading audio bytes: {}", exc)
        return None, MediaError.TRANSPORT_ERROR
    except asyncio.CancelledError:
        logger.warning("Audio download cancelled")
        raise
    except Exception as exc:
        logger.exception("Unexpected error downloading audio bytes: {}", exc)
        return None, MediaError.TRANSPORT_ERROR

    status = resp.status_code

    if status == 401 or status == 403:
        logger.error("Auth failed when fetching audio bytes (HTTP {}) — check META_ACCESS_TOKEN", status)
        return None, MediaError.AUTH_FAILED

    if status == 429:
        logger.warning("Rate-limited fetching audio bytes (HTTP 429)")
        return None, MediaError.RATE_LIMITED

    if status == 404:
        logger.error("Audio bytes URL returned 404 — media may have expired (5-min TTL)")
        return None, MediaError.INVALID_MEDIA_ID

    if not (200 <= status < 300):
        logger.error("Unexpected HTTP {} fetching audio bytes", status)
        return None, MediaError.DOWNLOAD_FAILED

    content_type = resp.headers.get("content-type", "")
    if not content_type.startswith(("audio/", "application/octet-stream", "video/")):
        # Explanation: Meta should return audio; anything else (HTML error page,
        # JSON error object) indicates something went wrong server-side.
        logger.warning(
            "Unexpected content-type '{}' when fetching audio bytes (status={}, body={})",
            content_type, status, resp.text[:300],
        )
        return None, MediaError.DOWNLOAD_FAILED

    data = resp.content
    if not data:
        logger.warning("Cloud API returned 2xx but body was empty for audio download")
        return None, MediaError.EMPTY_BODY

    return data, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def download_media_bytes(media_id: str) -> Optional[bytes]:
    """Return raw audio bytes from the WhatsApp Cloud API, or None on failure.

    Implements the mandatory two-step flow:
        1. GET /<PHONE_NUMBER_ID>/media/<media_id>  →  temporary upload URL
        2. GET <temporary URL>                      →  raw media bytes

    Returns None on any failure so callers can detect both absence of data
    and inspect the specific failure mode.
    """
    logger.info("Starting media download for media_id={}", media_id)
    t0 = time.monotonic()

    client = get_http_client()

    remote_url, err1 = await _resolve_media_url(media_id, client)
    if err1 is not None:
        logger.warning("Step-1 failed for media_id={}: {}", media_id, err1.value)
        return None

    data, err2 = await _fetch_audio_bytes(remote_url, client)
    if err2 is not None:
        logger.warning("Step-2 failed for media_id={}: {}", media_id, err2.value)
        return None

    elapsed = time.monotonic() - t0
    logger.info(
        "Media download complete for media_id={}: {} bytes in {:.2f}s",
        media_id, len(data), elapsed,
    )
    return data
