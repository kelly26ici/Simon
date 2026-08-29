"""Tests for get_embeddings in src/tools/embeddings.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.embeddings import get_embeddings


@pytest.mark.asyncio
async def test_get_embeddings_empty_input():
    res = await get_embeddings([])
    assert res == []


@pytest.mark.asyncio
async def test_get_embeddings_whitespace_only():
    res = await get_embeddings(["   ", ""])
    assert res == []


@pytest.mark.asyncio
async def test_get_embeddings_cloudflare_success():
    fake_vector = [0.1] * 1024
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"result": {"data": [fake_vector]}}
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("src.tools.embeddings.get_http_client", return_value=mock_client), \
         patch("src.tools.embeddings.CLOUDFLARE_ACCOUNT_ID", "cf_acc_123"), \
         patch("src.tools.embeddings.CLOUDFLARE_API_TOKEN", "cf_tok_123"):
        res = await get_embeddings(["Modern villa in Karen"])
        assert len(res) == 1
        assert len(res[0]) == 1024
