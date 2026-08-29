"""Tests for MpesaAgentClient in src/tools/mpesa/client.py."""

import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.mpesa.client import MpesaAgentClient


@pytest.mark.asyncio
async def test_get_oauth_token_cached():
    client = MpesaAgentClient()
    client._cached_token = "cached_test_token"
    client._token_expires_at = time.monotonic() + 3000
    token = await client.generate_access_token()
    assert token == "cached_test_token"


@pytest.mark.asyncio
async def test_get_oauth_token_fetches_new():
    client = MpesaAgentClient()
    client._cached_token = None
    client._token_expires_at = 0.0

    mock_resp = {"access_token": "new_fresh_token", "expires_in": "3599"}
    with patch.object(client, "_fetch_access_token", new=AsyncMock(return_value=mock_resp)):
        token = await client.generate_access_token()
        assert token == "new_fresh_token"
