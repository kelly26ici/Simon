"""Tests for handle_audio pipeline in src/messages/audios/audio_handler.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.messages.audios.audio_handler import handle_audio


@pytest.mark.asyncio
async def test_handle_audio_missing_audio_object():
    sender = "254700000000"
    raw_msg = {"id": "wamid.123"}
    with patch("src.messages.audios.audio_handler.send_whatsapp_message", new=AsyncMock()) as mock_send:
        await handle_audio(sender, raw_msg)
        mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_audio_missing_media_id():
    sender = "254700000000"
    raw_msg = {"id": "wamid.123", "audio": {}}
    with patch("src.messages.audios.audio_handler.send_whatsapp_message", new=AsyncMock()) as mock_send:
        await handle_audio(sender, raw_msg)
        mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_audio_successful_flow():
    sender = "254700000000"
    raw_msg = {"id": "wamid.123", "audio": {"id": "media_456", "mime_type": "audio/ogg"}}
    fake_audio_bytes = b"OggS" + b"\x00" * 50

    with patch("src.messages.audios.audio_handler.download_media_bytes", new=AsyncMock(return_value=fake_audio_bytes)), \
         patch("src.messages.audios.audio_handler.normalise_audio", return_value=b"RIFF" + b"\x00" * 50), \
         patch("src.messages.audios.audio_handler.transcribe_audio", new=AsyncMock(return_value="3 bedroom house")), \
         patch("src.messages.audios.audio_handler.handle_text", new=AsyncMock()) as mock_handle_text:
        
        await handle_audio(sender, raw_msg)
        mock_handle_text.assert_awaited_once()
