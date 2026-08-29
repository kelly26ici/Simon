"""Tests for download_media_bytes() HTTP behavior (mocked)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.messages.downloader import download_media_bytes


@pytest.mark.asyncio
async def test_download_returns_bytes_on_success():
    media_id = "test-media-id"
    fake_bytes = b"\xff\xd8\xff"

    mock_response_1 = MagicMock()
    mock_response_1.status_code = 200
    mock_response_1.json.return_value = {"url": "https://cdn.example.com/media.jpg"}
    mock_response_1.raise_for_status = MagicMock()

    mock_response_2 = MagicMock()
    mock_response_2.status_code = 200
    mock_response_2.content = fake_bytes
    mock_response_2.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[mock_response_1, mock_response_2])
    mock_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await download_media_bytes(media_id)

    assert result == fake_bytes


@pytest.mark.asyncio
async def test_download_returns_none_on_failure():
    import httpx
    media_id = "bad-media-id"

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {}

    mock_client = AsyncMock()
    exc = httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=mock_resp)
    mock_client.get = AsyncMock(side_effect=exc)
    mock_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await download_media_bytes(media_id)

    assert result is None
