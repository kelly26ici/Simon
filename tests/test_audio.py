"""
Unit tests for voice-note handling.

Covers:
- Audio message detection / routing (downloader + handler wiring)
- Transcription success (transcript flows through the text path)
- Transcription failure (graceful fallback, no crash)
- Temp file cleanup after processing
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.messages.audios.transcriber import transcribe_audio
from src.messages.audios.audio_handler import handle_audio, GRACEFUL_FALLBACK
from src.messages.downloader import download_media_bytes


# ─── Audio detection / routing ────────────────────────────────────────────────


def test_audio_message_routes_to_handler():
    """The router must dispatch 'audio' messages to the audio handler."""
    from src.messages.router import MESSAGE_HANDLERS
    from src.messages.audios.audio_handler import handle_audio

    assert MESSAGE_HANDLERS["audio"] is handle_audio


# ─── Transcription success ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transcription_success_flows_through_text_path(tmp_path):
    """A successful transcript is fed through the text handler as a user message."""
    audio_bytes = b"fake-audio-bytes"
    transcript = "Hello, I am looking for a two bedroom apartment."

    with patch(
        "src.messages.audios.audio_handler.download_media_bytes",
        AsyncMock(return_value=audio_bytes),
    ), patch(
        "src.messages.audios.audio_handler.transcribe_audio",
        AsyncMock(return_value=transcript),
    ), patch(
        "src.messages.audios.audio_handler.handle_text",
        AsyncMock(return_value=None),
    ) as mock_handle_text:

        await handle_audio("254700000000", {
            "id": "wamid.AUDIO_1",
            "audio": {"id": "media_123", "mime_type": "audio/ogg"},
        })

        # The transcript must reach the SAME pipeline as a normal text message.
        mock_handle_text.assert_awaited_once()
        call_sender, call_msg = mock_handle_text.await_args.args
        assert call_sender == "254700000000"
        assert call_msg["text"]["body"] == transcript
        assert call_msg["id"] == "wamid.AUDIO_1"


# ─── Transcription failure ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transcription_failure_sends_fallback(tmp_path):
    """When transcription fails, send a graceful fallback instead of crashing."""
    with patch(
        "src.messages.audios.audio_handler.download_media_bytes",
        AsyncMock(return_value=b"fake-audio-bytes"),
    ), patch(
        "src.messages.audios.audio_handler.transcribe_audio",
        AsyncMock(return_value=None),
    ), patch(
        "src.messages.audios.audio_handler.send_whatsapp_message",
        AsyncMock(return_value=None),
    ) as mock_send:

        await handle_audio("254700000000", {
            "audio": {"id": "media_123", "mime_type": "audio/ogg"},
        })

        mock_send.assert_awaited_once()
        to, text = mock_send.await_args.args
        assert to == "254700000000"
        assert text == GRACEFUL_FALLBACK


@pytest.mark.asyncio
async def test_download_failure_sends_fallback():
    """When media download fails, send a graceful fallback instead of crashing."""
    with patch(
        "src.messages.audios.audio_handler.download_media_bytes",
        AsyncMock(return_value=None),
    ), patch(
        "src.messages.audios.audio_handler.send_whatsapp_message",
        AsyncMock(return_value=None),
    ) as mock_send:

        await handle_audio("254700000000", {
            "audio": {"id": "media_123", "mime_type": "audio/ogg"},
        })

        mock_send.assert_awaited_once()
        to, text = mock_send.await_args.args
        assert to == "254700000000"
        assert text == GRACEFUL_FALLBACK


@pytest.mark.asyncio
async def test_missing_media_id_sends_fallback():
    """An audio message without a media id is handled gracefully."""
    with patch(
        "src.messages.audios.audio_handler.send_whatsapp_message",
        AsyncMock(return_value=None),
    ) as mock_send:

        await handle_audio("254700000000", {"audio": {}})

        mock_send.assert_awaited_once()
        to, text = mock_send.await_args.args
        assert text == GRACEFUL_FALLBACK


# ─── Temp file cleanup ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_temp_audio_file_cleaned_up(monkeypatch, tmp_path):
    """The downloaded audio temp file is removed after processing."""
    audio_file = tmp_path / "samantha_audio_test.ogg"
    audio_file.write_bytes(b"fake-audio-bytes")

    async def fake_write(data, mime):
        return audio_file

    monkeypatch.setattr(
        "src.messages.audios.audio_handler._write_temp_audio",
        lambda data, mime: audio_file,
    )

    with patch(
        "src.messages.audios.audio_handler.download_media_bytes",
        AsyncMock(return_value=b"fake-audio-bytes"),
    ), patch(
        "src.messages.audios.audio_handler.transcribe_audio",
        AsyncMock(return_value="transcript"),
    ), patch(
        "src.messages.audios.audio_handler.handle_text",
        AsyncMock(return_value=None),
    ):

        await handle_audio("254700000000", {
            "audio": {"id": "media_123", "mime_type": "audio/ogg"},
        })

        # The temp file must be gone after processing.
        assert not audio_file.exists()


# ─── Downloader ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_media_bytes_success():
    """download_media_bytes resolves the media URL then fetches the bytes."""
    from unittest.mock import Mock

    fake_url = "https://graph.example.com/audio/xyz"

    # Explanation: We configure status_code explicitly because the
    # improved downloader now checks each status code branch individually.
    meta_resp = Mock()
    meta_resp.raise_for_status = Mock()
    meta_resp.status_code = 200
    meta_resp.headers = {"content-type": "application/json"}
    meta_resp.json = Mock(return_value={"url": fake_url})

    data_resp = Mock()
    data_resp.raise_for_status = Mock()
    data_resp.status_code = 200
    data_resp.headers = {"content-type": "audio/ogg"}
    data_resp.content = b"the-audio-bytes"

    async def fake_get(url, headers=None, timeout=None):
        if url == fake_url:
            return data_resp
        return meta_resp

    fake_client = AsyncMock()
    fake_client.get.side_effect = fake_get
    fake_client.aclose = AsyncMock()

    with patch(
        "src.messages.downloader.httpx.AsyncClient", return_value=fake_client
    ):
        result = await download_media_bytes("media_123")

    assert result == b"the-audio-bytes"
    assert fake_client.get.await_count == 2
    fake_client.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_download_media_bytes_missing_url_returns_none(tmp_path):
    """If the metadata response lacks a url, return None (no crash)."""
    from unittest.mock import Mock

    fake_client = AsyncMock()
    meta_resp = Mock()
    meta_resp.raise_for_status = Mock()
    meta_resp.json = Mock(return_value={})
    fake_client.get.return_value = meta_resp
    fake_client.aclose = AsyncMock()

    with patch(
        "src.messages.downloader.httpx.AsyncClient", return_value=fake_client
    ):
        result = await download_media_bytes("media_123")

    assert result is None
    # Step-2 must never be called when step-1 has no url.
    assert fake_client.get.await_count == 1
    fake_client.aclose.assert_called_once()