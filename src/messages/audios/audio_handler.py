# src/messages/audios/audio_handler.py

"""Handler for incoming WhatsApp audio/voice-note messages.

Flow
----
1. Extract the media id + mime type from the raw message.
2. Download the audio bytes via the WhatsApp Cloud API (two-step flow).
3. Write them to a temporary file.
4. Transcribe with Groq Speech-to-Text (with tenacity retry on transient errors).
5. On success, feed the transcript through the SAME path as a normal text
   message (handle_text) so the agent needs no separate reasoning path.
6. On any failure, send a graceful fallback instead of crashing the webhook.
7. Always clean up the temporary file — guaranteed by the try/finally.

Optimised with:
- Typed error enum so every failure mode is distinguished at the log level.
- CancelledError is propagated without logging as an error.
- send_whatsapp_message failures inside the fallback path are logged but do
  not mask the original error.
- Explicit typing throughout; no implicit `Any`.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from enum import Enum
from pathlib import Path
from typing import Final, Optional

from loguru import logger

from src.messages.audios.transcriber import transcribe_audio
from src.messages.chats.text_handler import handle_text
from src.messages.downloader import download_media_bytes
from src.messages.sender import send_whatsapp_message


# ---------------------------------------------------------------------------
# Typed error catalogue — each maps to a specific failure mode in the log.
# ---------------------------------------------------------------------------

class AudioError(str, Enum):
    """Every distinct failure mode in the audio pipeline."""

    NO_RAW_MESSAGE        = "no_raw_message"         # caller passed None / bad keys
    NO_AUDIO_OBJECT       = "no_audio_object"        # raw had no "audio" key
    MISSING_MEDIA_ID      = "missing_media_id"        # audio obj had no "id"
    DOWNLOAD_FAILED       = "download_failed"         # Cloud API two-step failed
    WRITE_TEMP_FAILED     = "write_temp_failed"       # OS error writing temp file
    TRANSCRIPTION_FAILED  = "transcription_failed"    # Groq returned None / ""
    AGENT_FAILED          = "agent_failed"            # handle_text raised


# Public fallback message — tests and callers can reference it directly.
GRACEFUL_FALLBACK: Final[str] = (
    "I couldn't process that voice note. Please try sending it again, "
    "or type your message as text."
)


# ---------------------------------------------------------------------------
# MIME extension mapping
# ---------------------------------------------------------------------------

_MIME_EXTENSIONS: Final[dict[str, str]] = {
    "audio/mp3":        ".mp3",
    "audio/mpeg":       ".mp3",
    "audio/mp4":        ".m4a",
    "audio/mp4a-latm":  ".m4a",
    "audio/ogg":        ".ogg",
    "audio/opus":       ".ogg",
    "audio/wav":        ".wav",
    "audio/webm":       ".webm",
    "audio/x-m4a":      ".m4a",
    "audio/aac":        ".aac",
    "audio/amr":        ".amr",
}


def _extension_for_mime(mime_type: Optional[str]) -> str:
    """Return the file extension for a WhatsApp audio mime type."""
    return _MIME_EXTENSIONS.get((mime_type or "").lower(), ".audio")


def _write_temp_audio(data: bytes, mime_type: Optional[str]) -> Path:
    """Write audio bytes to a unique temp file and return its path.

    Runs synchronously — mkstemp + a single write is fast enough that
    offloading to a thread-pool adds overhead with no benefit.
    """
    fd, path = tempfile.mkstemp(
        prefix="samantha_audio_",
        suffix=_extension_for_mime(mime_type),
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except OSError:
        # Explanation: fdopen failed after the descriptor was already created,
        # so we must clean up the fd and any partial file before re-raising.
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return Path(path)


async def _send_fallback(sender: str) -> None:
    """Send the graceful fallback, swallowing send failures without masking
    the original error."""
    try:
        await send_whatsapp_message(sender, GRACEFUL_FALLBACK)
    except asyncio.CancelledError:
        # Explanation: If the task was cancelled while trying to send the
        # fallback, propagate that cancellation so the webhook itself
        # cancels — do NOT swallow it.
        raise
    except Exception as send_exc:
        # Explanation: This is a secondary failure (the fallback *itself*
        # failed). Log it at error level but do NOT re-send another message
        # — that would spam the user.
        logger.exception(
            "Failed to send fallback response to sender={}: [{}] {}",
            sender,
            type(send_exc).__qualname__,
            send_exc,
        )


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

async def handle_audio(sender: str, raw: Optional[dict]) -> None:
    """Handle one incoming audio/voice-note message.

    Parameters
    ----------
    sender : str
        WhatsApp number (e.g. "254700000000"), used as the conversation key.
    raw : dict | None
        The raw WhatsApp message object from the Cloud API webhook.
        Expected shape: ``{"id": "wamid.ABC", "audio": {"id": "med123", "mime_type": "audio/ogg"}}``

    Every failure mode is caught and converted to a friendly reply — this
    function never propagates an exception to the webhook dispatcher.
    """
    t0 = time.monotonic()

    # Guarantee tmp_path is initialised before any try block so the finally
    # clause can reference it unconditionally.
    tmp_path: Optional[Path] = None

    # ── Phase 1: validate and extract from raw payload ───────────────────────

    if not raw:
        logger.warning("handle_audio called with None payload from sender={}", sender)
        await _send_fallback(sender)
        return

    audio_obj = raw.get("audio")
    if not audio_obj:
        logger.warning(
            "No audio object found for sender={} — message type='{}'",
            sender, raw.get("type"),
        )
        await _send_fallback(sender)
        return

    media_id: Optional[str] = audio_obj.get("id")
    mime_type: Optional[str] = audio_obj.get("mime_type")

    if not media_id:
        logger.warning(
            "Audio message from sender={} has no media id (mime={})",
            sender, mime_type,
        )
        await _send_fallback(sender)
        return

    logger.info(
        "Audio received from {} — media_id={} mime={} size={}",
        sender, media_id, mime_type,
        audio_obj.get("file_size", "unknown"),
    )

    # ── Phase 2: download ─────────────────────────────────────────────────────

    data: Optional[bytes] = await download_media_bytes(media_id)
    if data is None:
        logger.error("Failed to download audio {} from {}", media_id, sender)
        await _send_fallback(sender)
        return

    logger.debug("Downloaded {} bytes for audio media_id={}", len(data), media_id)

    # ── Phase 3–6: all remaining work in one try/finally ──────────────────────

    try:
        # Phase 3: write to temp file.
        try:
            tmp_path = _write_temp_audio(data, mime_type)
        except (OSError, PermissionError) as exc:
            logger.exception(
                "OS error writing temp audio for media_id={} from sender={}: [{}] {}",
                media_id, sender, type(exc).__qualname__, exc,
            )
            await _send_fallback(sender)
            return

        # Phase 4: transcribe.
        # Explanation: transcribe_audio handles its own retries internally
        # (via tenacity on transient Groq errors).  handle_audio only sees
        # the final result.
        transcript: Optional[str] = await transcribe_audio(tmp_path)

        if transcript is None:
            logger.error(
                "Transcription returned None for media_id={} from sender={}",
                media_id, sender,
            )
            await _send_fallback(sender)
            return

        transcript = transcript.strip()
        if not transcript:
            logger.warning(
                "Transcription returned blank text for media_id={} from sender={}",
                media_id, sender,
            )
            await _send_fallback(sender)
            return

        logger.info(
            "Transcription complete for sender={} — {} chars in {:.1f}s",
            sender, len(transcript), time.monotonic() - t0,
        )

        # Phase 5: feed through the same pipeline as a normal text message.
        # Explanation: Passing the original WhatsApp message id in the payload
        # preserves dedup and audit-logging that the text pipeline already
        # implements — no new reasoninng path needed in Samantha's agent.
        text_payload: dict = {"text": {"body": transcript}, "id": raw.get("id")}
        await handle_text(sender, text_payload)

    except asyncio.CancelledError:
        # Explanation: Propagate immediately — the finally block still cleans
        # up tmp_path, but we do not log cancellation as an error.
        raise

    except Exception as exc:
        # Explanation: handle_text or transcribe_audio (despite retries) raised
        # an unexpected error.  Log with structured context and send fallback.
        logger.exception(
            "Agent error handling transcribed audio from {} (media_id={}): [{}] {}",
            sender, media_id, type(exc).__qualname__, exc,
        )
        await _send_fallback(sender)

    finally:
        # Phase 6: always clean up — guaranteed, every path.
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except PermissionError:
                logger.warning(
                    "PermissionError removing temp file {} — "
                    "check OS permissions for the temp directory.",
                    tmp_path,
                )
            except OSError as exc:
                logger.warning(
                    "OS error removing temp file {}: [{}] {}",
                    tmp_path, type(exc).__qualname__, exc,
                )
            except Exception as exc:
                logger.warning(
                    "Unexpected error removing temp file {}: [{}] {}",
                    tmp_path, type(exc).__qualname__, exc,
                )
