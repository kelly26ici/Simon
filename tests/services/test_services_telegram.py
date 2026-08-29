"""Tests for Telegram service functions in src/services/telegram.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.telegram import get_simon_chat_id, save_simon_chat_id, send_telegram_message


@pytest.mark.asyncio
async def test_get_simon_chat_id_from_env():
    import src.services.telegram as tel
    tel._cached_simon_chat_id = None
    with patch("src.services.telegram._telegram_store.get", new=AsyncMock(return_value=None)), \
         patch("src.services.telegram.db.get_owner_chat_id", new=AsyncMock(return_value=None)), \
         patch.dict("os.environ", {"SIMON_CHAT_ID": "999888777"}):
        chat_id = await get_simon_chat_id()
        assert chat_id == "999888777"


@pytest.mark.asyncio
async def test_save_simon_chat_id_persists_to_store():
    with patch("src.services.telegram._telegram_store.set", new=AsyncMock()) as mock_set, \
         patch("src.services.telegram.db.save_owner_chat_id", new=AsyncMock(return_value=True)):
        await save_simon_chat_id("11223344", username="simon", first_name="Simon")
        mock_set.assert_awaited()


@pytest.mark.asyncio
async def test_send_telegram_message_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("src.services.telegram.TELEGRAM_BOT_TOKEN", "fake_bot_token"), \
         patch("src.services.telegram.get_simon_chat_id", new=AsyncMock(return_value="12345")):
        success = await send_telegram_message("Hello Owner", chat_id="12345")
        assert success is True
