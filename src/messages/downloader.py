# src/messages/downloader.py

"""WhatsApp Cloud API media downloader — hardened.

Flow
----
1. GET ``/{graph_version}/{MEDIA_ID}`` → temporary upload URL
2. GET the URL → raw media bytes

Transient failures (timeouts, TCP resets, 5xx) are retried via tenacity up to
3 attempts with exponential back-off.  Permanent failures always stop the retry
loop immediately and return a typed ``MediaError`` so callers can react
appropriately:

- ``INVALID_MEDIA_ID``   — 400 / 404 in step-1 (bad id or >5 min TTL)
- ``AUTH_FAILED``        — 401 / 403 (bad/expired token)
- ``RATE_LIMITED``       — 429 from Meta
- ``DOWNLOAD_FAILED``    — other 2xx/4xx/5xx
- ``TRANSPORT_ERROR``    — ConnectError, Timeout, etc.
- ``EMPTY_BODY``         — 2xx but 0 bytes

A fresh ``httpx.AsyncClient`` is created and closed for every call so retries
start with a clean connection pool — no shared singleton.

The old implementation built the step-1 URL as
``/{version}/{PHONE_NUMBER_ID}/media/{MEDIA_ID}`` (the V11.0 REST-API form).
That path returns HTTP 400 on current Graph API versions (v20+) and was the
direct cause of the deployment failure.  The correct URL is
``/{version}/{MEDIA_ID}`` with no ``PHONE_NUMBER_ID`` segment.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

from src.configs.settings import (
    META_ACCESS_TOKEN,
    META_GRAPH_API_VERSION,
    META_GRAPH_BASE_URL,
)


# ---------------------------------------------------------------------------
# Result type & error catalogue
# (MediaError defined first — _PERMANENT_ERRORS references it at module
# load time, so order matters.)
# ---------------------------------------------------------------------------

class MediaError(str, Enum):
    """Every distinct failure mode in the download pipeline."""

    INVALID_MEDIA_ID = "invalid_media_id"   # 400/404 step-1 (or 404 step-2)
    AUTH_FAILED = "auth_failed"             # 401/403
    RATE_LIMITED = "rate_limited"           # 429
    DOWNLOAD_FAILED = "download_failed"     # other non-2xx
    TRANSPORT_ERROR = "transport_error"     # ConnectError, Timeout, etc.
    EMPTY_BODY = "empty_body"               # 2xx but 0 bytes


PERMANENT_ERRORS: frozenset[MediaError] = frozenset(
    {
        MediaError.INVALID_MEDIA_ID,
        MediaError.AUTH_FAILED,
        MediaError.RATE_LIMITED,
    }
)
"""Permanent errors — retrying is pointless and wastes time."""


@dataclass(frozen=True)
class MediaResult:
    """Immutable result of a single download attempt."""

    data: Optional[bytes]
    error: Optional[MediaError]

    @property
    def ok(self) -> bool:
        return self.data is not None and self.error is None


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------
#
# At most 3 attempts (original + 2 retries).
# Per-attempt backoff: 0.25 s → 1 s → 4 s (capped at max=8).
# Total worst-case wall time ≈ 5.25 s — well inside the Render free-tier
# 30 s HTTP timeout envelope.
#
_RETRY_STOP = stop_after_attempt(3)
_RETRY_WAIT = wait_exponential(multiplier=0.25, min=0.25, max=8)


def _retry_predicate(result: MediaResult) -> bool:
    """Return ``True`` to retry, ``False`` to stop and return the result."""
    return result.error not in PERMANENT_ERRORS and not result.ok


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers() -> dict[str, str]:
    """Authorization header for the Graph API."""
    return {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}


def _media_url(media_id: str) -> str:
    """Step-1 URL — resolve a media id to a temporary download URL.

    WhatsApp Cloud API get-specific-media endpoint (v20+)::

        GET /{GRAPH_API_VERSION}/{MEDIA_ID}

    **Important:** This does NOT include ``PHONE_NUMBER_ID`` as a path segment
    and is NOT ``/media/{MEDIA_ID}``.

    The old V11-style path ``/{version}/{phone_number_id}/media/{MEDIA_ID}``
    returns HTTP 400 on current Graph API versions and was the direct cause
    of the audio download failures in the Aug-12 deployment logs.
    """
    return f"{META_GRAPH_BASE_URL}/{META_GRAPH_API_VERSION}/{media_id}"


# ---------------------------------------------------------------------------
# Step-1: resolve media_id → temporary upload URL
# ---------------------------------------------------------------------------

async def _resolve_media_url(
    media_id: str,
    client: httpx.AsyncClient,
) -> MediaResult:
    """Resolve ``media_id`` to a one-shot download URL.

    On success the temporary URL is carried as an opaque ``bytes`` value in
    ``result.data`` (callers decode it with ``result.data.decode()`` after
    confirming ``result.ok``).
    """
    url = _media_url(media_id)
    try:
        resp = await client.get(url, headers=_headers(), timeout=10)
    except httpx.TimeoutException as exc:
        logger.warning("Timeout resolving media {}: {}", media_id, exc)
        return MediaResult(data=None, error=MediaError.TRANSPORT_ERROR)
    except httpx.NetworkError as exc:
        # Covers ConnectError, ReadError, WriteError, CloseError, etc.
        logger.warning("Network error resolving media {}: {}", media_id, exc)
        return MediaResult(data=None, error=MediaError.TRANSPORT_ERROR)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected error resolving media {}: [{}] {}",
            media_id,
            type(exc).__qualname__,
            exc,
        )
        return MediaResult(data=None, error=MediaError.TRANSPORT_ERROR)

    status = resp.status_code

    if status in (401, 403):
        logger.error(
            "Auth failure resolving {} (HTTP {}) — check META_ACCESS_TOKEN",
            media_id,
            status,
        )
        return MediaResult(data=None, error=MediaError.AUTH_FAILED)

    if status in (400, 404):
        logger.warning(
            "Media {} not available on Meta's servers (HTTP {})",
            media_id,
            status,
        )
        return MediaResult(data=None, error=MediaError.INVALID_MEDIA_ID)

    if status == 410:
        # Meta returns 410 when the 5-minute signed-URL TTL has expired.
        logger.error("Media {} has expired (HTTP 410 Gone)", media_id)
        return MediaResult(data=None, error=MediaError.INVALID_MEDIA_ID)

    if status == 429:
        retry_after = resp.headers.get("retry-after", "1")
        logger.warning(
            "Rate-limited resolving {} (HTTP 429, retry-after={})",
            media_id,
            retry_after,
        )
        return MediaResult(data=None, error=MediaError.RATE_LIMITED)

    if not (200 <= status < 300):
        logger.error("Unexpected HTTP {} resolving media {}", status, media_id)
        return MediaResult(data=None, error=MediaError.DOWNLOAD_FAILED)

    # Expect a JSON body with the temp URL.
    content_type = resp.headers.get("content-type", "")
    if not content_type.startswith("application/json"):
        logger.error(
            "Step-1 for {} returned non-JSON (type={}, status={}, body={})",
            media_id,
            content_type,
            status,
            resp.text[:200],
        )
        return MediaResult(data=None, error=MediaError.DOWNLOAD_FAILED)

    try:
        body = resp.json()
    except Exception as exc:
        logger.warning(
            "JSON parse failure in step-1 for {}: [{}] {}",
            media_id,
            type(exc).__qualname__,
            exc,
        )
        return MediaResult(data=None, error=MediaError.DOWNLOAD_FAILED)

    remote_url: Optional[str] = body.get("url")
    if not remote_url:
        logger.error(
            "Step-1 JSON for {} missing 'url' (body={})",
            media_id,
            str(body)[:200],
        )
        return MediaResult(data=None, error=MediaError.DOWNLOAD_FAILED)

    # Carry the URL as opaque bytes so callers extract it after .ok check.
    return MediaResult(data=remote_url.encode(), error=None)


# ---------------------------------------------------------------------------
# Step-2: fetch raw bytes from the temporary URL
# ---------------------------------------------------------------------------

async def _fetch_audio_bytes(
    remote_url: str,
    client: httpx.AsyncClient,
) -> MediaResult:
    """Download raw bytes from the temporary URL provided by step-1."""
    try:
        resp = await client.get(remote_url, headers=_headers(), timeout=60)
    except httpx.TimeoutException as exc:
        logger.warning("Timeout fetching audio bytes: {}", exc)
        return MediaResult(data=None, error=MediaError.TRANSPORT_ERROR)
    except httpx.NetworkError as exc:
        # Covers ConnectError, ReadError, WriteError, CloseError, etc.
        logger.warning("Network error fetching audio bytes: {}", exc)
        return MediaResult(data=None, error=MediaError.TRANSPORT_ERROR)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected error fetching audio bytes: [{}] {}",
            type(exc).__qualname__,
            exc,
        )
        return MediaResult(data=None, error=MediaError.TRANSPORT_ERROR)

    status = resp.status_code

    if status in (401, 403):
        logger.error("Auth failure fetching bytes (HTTP {})", status)
        return MediaResult(data=None, error=MediaError.AUTH_FAILED)

    if status == 404:
        logger.error(
            "Temporary URL returned 404 — may have expired (5-min TTL)"
        )
        return MediaResult(data=None, error=MediaError.INVALID_MEDIA_ID)

    if status == 429:
        logger.warning("Rate-limited fetching audio bytes (HTTP 429)")
        return MediaResult(data=None, error=MediaError.RATE_LIMITED)

    if not (200 <= status < 300):
        logger.error("Unexpected HTTP {} fetching audio bytes", status)
        return MediaResult(data=None, error=MediaError.DOWNLOAD_FAILED)

    content_type = resp.headers.get("content-type", "")
    acceptable = ("audio/", "application/octet-stream", "video/")
    if not any(content_type.startswith(p) for p in acceptable):
        # Meta should return audio; HTML/JSON = server-side error.
        logger.warning(
            "Unexpected content-type '{}' in step-2 (HTTP {}, body={})",
            content_type,
            status,
            resp.text[:300],
        )
        return MediaResult(data=None, error=MediaError.DOWNLOAD_FAILED)

    data = resp.content
    if not data:
        logger.warning("Step-2 returned 2xx but empty body")
        return MediaResult(data=None, error=MediaError.EMPTY_BODY)

    return MediaResult(data=data, error=None)


# ---------------------------------------------------------------------------
# Orchestration — step-1 + step-2 + tenacity retry
# ---------------------------------------------------------------------------

async def _download_with_client(
    media_id: str,
    client: httpx.AsyncClient,
) -> MediaResult:
    """Run both steps using the provided client."""
    step1 = await _resolve_media_url(media_id, client)
    if not step1.ok:
        return step1

    # Extract the URL from the opaque bytes from step-1.
    remote_url: str = step1.data.decode()
    return await _fetch_audio_bytes(remote_url, client)


@retry(
    retry=retry_if_result(_retry_predicate),
    stop=_RETRY_STOP,
    wait=_RETRY_WAIT,
    reraise=True,
)
async def _download_attempt(
    media_id: str,
    client: httpx.AsyncClient,
) -> MediaResult:
    """One download attempt — tenacity calls this up to 3 times total."""
    return await _download_with_client(media_id, client)


async def download_media_bytes(media_id: str) -> Optional[bytes]:
    """Return raw audio bytes from the WhatsApp Cloud API, or ``None``.

    Retries (up to 3 attempts) on transient failures only:
    ``TRANSPORT_ERROR``, ``DOWNLOAD_FAILED``, ``EMPTY_BODY``.
    Permanent failures (invalid id, auth, rate-limited) stop immediately.

    A fresh ``httpx.AsyncClient`` is created and closed for every call so each
    attempt starts with a clean connection pool.
    """
    logger.info("Starting media download for media_id={}", media_id)
    t0 = time.monotonic()

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
    )
    try:
        result = await _download_attempt(media_id, client)
    except Exception as exc:
        # tenacity reraise=True exhausted retries, or CancelledError leaked.
        logger.error(
            "download_media_bytes exhausted for {}: [{}] {}",
            media_id,
            type(exc).__qualname__,
            exc,
        )
        return None
    finally:
        await client.aclose()

    if not result.ok:
        logger.warning(
            "download_media_bytes permanent failure for {}: {}",
            media_id,
            result.error.value,
        )
        return None

    elapsed = time.monotonic() - t0
    logger.info(
        "download_media_bytes complete for {}: {} bytes in {:.2f}s",
        media_id,
        len(result.data),
        elapsed,
    )
    return result.data
