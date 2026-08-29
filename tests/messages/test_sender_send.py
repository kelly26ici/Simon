"""Tests for send_whatsapp_message() in src/messages/sender.py."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.messages.sender import send_whatsapp_message


@pytest.mark.asyncio
async def test_send_whatsapp_message_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"messages": [{"id": "wamid.abc123"}]}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("src.messages.sender.get_http_client", return_value=mock_client):
        # Should complete without error
        await send_whatsapp_message("254700000000", "Hello!")
        mock_client.post.assert_awaited()
