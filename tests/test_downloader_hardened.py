# tests/test_downloader_hardened.py
"""Hardened tests for src/messages/downloader.py

Run with: pytest tests/test_downloader_hardened.py -v --asyncio-mode=auto
"""
from __future__ import annotations

import asyncio
import httpx
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.messages.downloader import (
    DOWNLOAD_FAILED,
    EMPTY_BODY,
    INVALID_MEDIA_ID,
    AUTH_FAILED,
    MediaError,
    PERMANENT_ERRORS,
    RATE_LIMITED,
    TRANSPORT_ERROR,
    _fetch_audio_bytes,
    _media_url,
    _resolve_media_url,
    _download_attempt,
    download_media_bytes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resp(status, json_body=None, text="", ctype="application/json", content=b""):
    """Build a fake httpx.Response."""
    r = Mock()
    r.status_code = status
    r.headers = {"content-type": ctype}
    r.text = text
    r.content = content
    r.raise_for_status = Mock()
    if json_body is not None:
        r.json = Mock(return_value=json_body)
    return r


def _client(*mock_responses):
    """Build a fake httpx.AsyncClient.

    Each positional argument is a response object (in order) that
    ``client.get`` will return on successive calls.

    **Important:** ``client.get`` is an **AsyncMock**, not a plain Mock,
    so `await client.get(...)` works without TypeError and the function
    under test can reach its own exception/error-handling branches.
    """
    c = AsyncMock()
    c.get = AsyncMock(side_effect=list(mock_responses))
    c.aclose = AsyncMock()
    return c


def _run(coro):
    """Run a coroutine in a fresh event loop (avoids pytest-asyncio
    strict-mode conflicts when some tests use plain `asyncio.run`)."""
    try:
        loop = asyncio.get_running_loop()
        # We're already inside an event loop — nest with ensure_future.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(asyncio.run, coro)
            return fut.result()
    except RuntimeError:
        return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Typed error shorthands — keep them locally bound so this module stays
# valid even if the underlying enum names change in downloader.py.
# ---------------------------------------------------------------------------
E = MediaError  # local alias; test reads as `E.INVALID_MEDIA_ID`
_INVALID = E.INVALID_MEDIA_ID
_AUTH = E.AUTH_FAILED
_RATE = E.RATE_LIMITED
_DL = E.DOWNLOAD_FAILED
_XPORT = E.TRANSPORT_ERROR
_EMPTY = E.EMPTY_BODY


# ---------------------------------------------------------------------------
# URL builder — this was the root cause of the Aug-12 bug
# ---------------------------------------------------------------------------

class TestMediaUrl:

    def test_url_format_has_no_phone_number_id(self):
        """Correct URL: /{GRAPH_API_VERSION}/{MEDIA_ID} (no PHONE_NUMBER_ID,
        no /media/ segment).  The old code embedded both and Meta answered
        HTTP 400 for every voice note in the deployed logs."""
        from src.configs.settings import (
            META_GRAPH_API_VERSION, META_GRAPH_BASE_URL, META_PHONE_NUMBER_ID,
        )
        url = _media_url("abc123")
        expected = f"{META_GRAPH_BASE_URL}/{META_GRAPH_API_VERSION}/abc123"
        assert url == expected
        assert "/media/" not in url
        assert META_PHONE_NUMBER_ID not in url

    def test_url_ends_with_raw_media_id(self):
        url = _media_url("wamid.ABC.123")
        assert url.endswith("/wamid.ABC.123")


# ---------------------------------------------------------------------------
# Step-1: _resolve_media_url
# ---------------------------------------------------------------------------

class TestResolveMediaUrl:

    def _call(self, media_id, client):
        return _run(_resolve_media_url(media_id, client))

    def test_200_missing_url_returns_download_failed(self):
        client = _client(_resp(200, json_body={}))
        assert self._call("media_123", client).error == _DL

    def test_400_returns_invalid_media_id(self):
        client = _client(_resp(400))
        assert self._call("m", client).error == _INVALID

    def test_401_returns_auth_failed(self):
        client = _client(_resp(401))
        assert self._call("m", client).error == _AUTH

    def test_403_returns_auth_failed(self):
        client = _client(_resp(403))
        assert self._call("m", client).error == _AUTH

    def test_404_returns_invalid_media_id(self):
        client = _client(_resp(404))
        assert self._call("m", client).error == _INVALID

    def test_410_returns_invalid_media_id(self):
        client = _client(_resp(410))
        assert self._call("m", client).error == _INVALID

    def test_429_returns_rate_limited(self):
        resp = _resp(429)
        resp.headers["retry-after"] = "2"
        client = _client(resp)
        assert self._call("m", client).error == _RATE

    def test_500_returns_download_failed_single_call(self):
        client = _client(_resp(500))
        r = self._call("media_123", client)
        assert r.error == _DL
        assert client.get.call_count == 1

    def test_503_returns_download_failed_single_call(self):
        client = _client(_resp(503))
        r = self._call("media_123", client)
        assert r.error == _DL
        assert client.get.call_count == 1

    def test_timeout_returns_transport_error(self):
        client = _client(httpx.TimeoutException("boom"))
        assert self._call("m", client).error == _XPORT

    def test_connect_error_returns_transport_error(self):
        client = _client(httpx.ConnectError("refused"))
        assert self._call("m", client).error == _XPORT

    def test_success_returns_url_as_opaque_bytes(self):
        url = "https://cdn.example.com/tmp/audio/xyz"
        client = _client(_resp(200, json_body={"url": url}))
        r = self._call("media_123", client)
        assert r.ok
        assert r.data == url.encode()

    def test_non_json_response_returns_download_failed(self):
        client = _client(_resp(200, ctype="text/html",
                               text="err", content=b"err"))
        assert self._call("m", client).error == _DL


# ---------------------------------------------------------------------------
# Step-2: _fetch_audio_bytes
# ---------------------------------------------------------------------------

class TestFetchAudioBytes:

    def _call(self, url, client):
        return _run(_fetch_audio_bytes(url, client))

    def test_ogg_returns_bytes(self):
        client = _client(_resp(200, ctype="audio/ogg", content=b"ogg"))
        assert self._call("https://cdn/x", client).data == b"ogg"

    def test_mpeg_accepted(self):
        client = _client(_resp(200, ctype="audio/mpeg", content=b"mp3"))
        assert self._call("u", client).ok

    def test_mp4a_latm_accepted(self):
        client = _client(_resp(200, ctype="audio/mp4a-latm",
                               content=b"m4a"))
        assert self._call("u", client).ok

    def test_wav_accepted(self):
        client = _client(_resp(200, ctype="audio/wav", content=b"wav"))
        assert self._call("u", client).ok

    def test_amr_accepted(self):
        client = _client(_resp(200, ctype="audio/amr", content=b"amr"))
        assert self._call("u", client).ok

    def test_octet_stream_accepted(self):
        client = _client(_resp(200, ctype="application/octet-stream",
                               content=b"bin"))
        assert self._call("u", client).ok

    def test_html_rejected(self):
        client = _client(_resp(200, ctype="text/html",
                               text="err", content=b"err"))
        assert self._call("u", client).error == _DL

    def test_json_error_rejected(self):
        client = _client(_resp(200, ctype="application/json",
                               json_body={"error": "not found"}))
        assert self._call("u", client).error == _DL

    def test_404_returns_invalid_media_id(self):
        client = _client(_resp(404))
        assert self._call("u", client).error == _INVALID

    def test_401_returns_auth_failed(self):
        client = _client(_resp(401))
        assert self._call("u", client).error == _AUTH

    def test_timeout_returns_transport_error(self):
        client = _client(httpx.TimeoutException("boom"))
        assert self._call("u", client).error == _XPORT

    def test_network_error_returns_transport_error(self):
        client = _client(httpx.NetworkError("net err"))
        assert self._call("u", client).error == _XPORT

    def test_empty_body_returns_empty_body_error(self):
        client = _client(_resp(200, ctype="audio/ogg", content=b""))
        assert self._call("u", client).error == _EMPTY


# ---------------------------------------------------------------------------
# Retry / orchestration via tenacity
# ---------------------------------------------------------------------------

class TestRetry:

    def _call(self, media_id, client):
        return _run(_download_attempt(media_id, client))

    def test_transport_error_retries_three_times(self):
        client = _client(
            httpx.TimeoutException("boom"),
            httpx.TimeoutException("boom"),
            httpx.TimeoutException("boom"),
        )
        r = self._call("media_123", client)
        assert r.error == _XPORT
        assert client.get.call_count == 3

    def test_empty_body_retries_three_times(self):
        temp_url = "https://cdn.example.com/tmp/x"
        client = _client(
            _resp(200, json_body={"url": temp_url}),
            _resp(200, ctype="audio/ogg", content=b""),
            _resp(200, json_body={"url": temp_url}),
            _resp(200, ctype="audio/ogg", content=b""),
            _resp(200, json_body={"url": temp_url}),
            _resp(200, ctype="audio/ogg", content=b""),
        )
        r = self._call("media_123", client)
        assert r.error == _EMPTY
        assert client.get.call_count == 6

    def test_500_retries_three_times(self):
        client = _client(
            _resp(500), _resp(500), _resp(500),
        )
        r = self._call("media_123", client)
        assert r.error == _DL
        assert client.get.call_count == 3

    def test_400_no_retry_single_attempt(self):
        client = _client(_resp(400))
        r = self._call("media_123", client)
        assert r.error == _INVALID
        assert client.get.call_count == 1

    def test_401_no_retry_single_attempt(self):
        client = _client(_resp(401))
        r = self._call("media_123", client)
        assert r.error == _AUTH
        assert client.get.call_count == 1

    def test_429_no_retry_single_attempt(self):
        client = _client(_resp(429))
        r = self._call("media_123", client)
        assert r.error == _RATE
        assert client.get.call_count == 1

    def test_success_after_two_transient_failures(self):
        """Two timeouts then success: 4 total HTTP calls, bytes returned."""
        temp_url = "https://cdn.example.com/tmp/x"
        client = _client(
            httpx.TimeoutException("boom"),
            httpx.TimeoutException("boom"),
            _resp(200, json_body={"url": temp_url}),
            _resp(200, ctype="audio/ogg", content=b"data"),
        )
        r = self._call("media_123", client)
        assert r.data == b"data"
        assert client.get.call_count == 4


# ---------------------------------------------------------------------------
# PERMANENT_ERRORS frozenset semantics
# ---------------------------------------------------------------------------

class TestPermanentErrors:

    def test_invalid_media_id_is_permanent(self):
        assert E.INVALID_MEDIA_ID in PERMANENT_ERRORS

    def test_auth_failed_is_permanent(self):
        assert E.AUTH_FAILED in PERMANENT_ERRORS

    def test_rate_limited_is_permanent(self):
        assert E.RATE_LIMITED in PERMANENT_ERRORS

    def test_transport_error_is_retryable(self):
        assert E.TRANSPORT_ERROR not in PERMANENT_ERRORS

    def test_download_failed_is_retryable(self):
        assert E.DOWNLOAD_FAILED not in PERMANENT_ERRORS

    def test_empty_body_is_retryable(self):
        assert E.EMPTY_BODY not in PERMANENT_ERRORS


# ---------------------------------------------------------------------------
# End-to-end: download_media_bytes orchestration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDownloadMediaBytes:

    async def _call(self, media_id, mock_client):
        with patch(
            "src.messages.downloader.httpx.AsyncClient",
            return_value=mock_client,
        ):
            return await download_media_bytes(media_id)

    async def test_full_success_returns_bytes(self):
        temp_url = "https://cdn.example.com/tmp/abc"
        client = _client(
            _resp(200, json_body={"url": temp_url}),
            _resp(200, ctype="audio/ogg", content=b"ogg-bytes"),
        )
        result = await self._call("media_123", client)
        assert result == b"ogg-bytes"
        assert client.get.call_count == 2
        client.aclose.assert_called_once()

    async def test_aclose_on_success(self):
        temp_url = "https://cdn.example.com/tmp/abc"
        client = _client(
            _resp(200, json_body={"url": temp_url}),
            _resp(200, ctype="audio/ogg", content=b"data"),
        )
        await self._call("media_123", client)
        client.aclose.assert_called_once()

    async def test_step1_404_stops_before_step2(self):
        client = _client(_resp(404))
        result = await self._call("media_123", client)
        assert result is None
        assert client.get.call_count == 1

    async def test_step1_missing_url_stops_before_step2(self):
        client = _client(
            _resp(200, json_body={}),
            _resp(200, json_body={}),
            _resp(200, json_body={}),
        )
        result = await self._call("media_123", client)
        assert result is None
        assert client.get.call_count == 3

    async def test_non_json_step1_returns_none(self):
        client = _client(
            _resp(200, ctype="text/html", text="err", content=b"err"),
            _resp(200, ctype="text/html", text="err", content=b"err"),
            _resp(200, ctype="text/html", text="err", content=b"err"),
        )
        result = await self._call("media_123", client)
        assert result is None

    async def test_aclose_on_step1_failure(self):
        client = _client(_resp(400))
        await self._call("media_123", client)
        client.aclose.assert_called_once()

    async def test_aclose_on_exhausted_retries(self):
        client = _client(_resp(500), _resp(500), _resp(500))
        await self._call("media_123", client)
        client.aclose.assert_called_once()

    async def test_retry_on_transient_then_success(self):
        temp_url = "https://cdn.example.com/tmp/x"
        client = _client(
            httpx.TimeoutException("boom"),
            httpx.TimeoutException("boom"),
            _resp(200, json_body={"url": temp_url}),
            _resp(200, ctype="audio/ogg", content=b"data"),
        )
        result = await self._call("media_123", client)
        assert result == b"data"
        assert client.get.call_count == 4
        client.aclose.assert_called_once()
