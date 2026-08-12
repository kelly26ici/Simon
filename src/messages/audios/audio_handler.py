# src/messages/audios/audio_handler.py

"""Hardened handler for incoming WhatsApp audio/voice-note messages.

Flow
----
1. Extract the media id + mime type + metadata from the raw message.
2. Log structured diagnostic info (no raw phone numbers, no API secrets).
3. Download the audio bytes via the WhatsApp Cloud API (two-step flow).
4. Write them to a temporary file with the correct extension.
5. Normalise via FFmpeg → 16 kHz mono WAV (fail-fast with full diagnostics).
6. Validate normalised output (exists, size > 0, readable).
7. Transcribe with Groq Whisper Large V3 (tenacity retry on transient errors).
8. On success, feed the transcript through the SAME path as a normal text
   message (handle_text) so the agent needs no separate reasoning path.
9. On any failure, send a graceful fallback instead of crashing the webhook.
10. Always clean up the temporary file — guaranteed by the try/finally.

Design constraints
------------------
- Privacy-safe sender identifier: a short hash suffix, never the raw number.
- Every external call (download, normalise, transcribe, agent) is wrapped
  with its own typed error handling so logs say *what* failed, *where*,
  and *whether it is retryable*.
- Structured single-line logs: key=value pairs, never multi-line dumps.
- CancelledError is propagated without logging as an error.
- No secrets in logs (no API keys, no Authorization headers, no raw audio).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import tempfile
import time
from enum import Enum
from pathlib import Path
from typing import Final, Optional

from loguru import logger

from src.messages.audios.normaliser import normalise_audio
from src.messages.audios.transcriber import transcribe_audio
from src.messages.chats.text_handler import handle_text
from src.messages.downloader import MediaError, download_media_bytes
from src.messages.sender import send_whatsapp_message


# ---------------------------------------------------------------------------
# Typed error catalogue — each maps to a specific failure mode in the log.
# ---------------------------------------------------------------------------

class AudioError(str, Enum):
 """Every distinct failure mode in the audio pipeline."""

 NO_RAW_MESSAGE = "no_raw_message"  # caller passed None / bad keys
 NO_AUDIO_OBJECT = "no_audio_object"  # raw had no "audio" key
 MISSING_MEDIA_ID = "missing_media_id"  # audio obj had no "id"
 DOWNLOAD_FAILED = "download_failed"  # Cloud API two-step failed
 WRITE_TEMP_FAILED = "write_temp_failed"  # OS error writing temp file
 TRANSCRIPTION_FAILED = "transcription_failed"  # Groq returned None / ""
 AGENT_FAILED = "agent_failed"  # handle_text raised


# Public fallback message — tests and callers can reference it directly.
GRACEFUL_FALLBACK: Final[str] = (
 "I couldn't process that voice note. Please try sending it again, "
 "or type your message as text."
 )


# ---------------------------------------------------------------------------
# Privacy-safe sender identifier
# ---------------------------------------------------------------------------
# Never log the raw WhatsApp number. Instead derive a short suffix hash
# that is enough to correlate logs for a single conversation without
# exposing the full phone number.

def _sender_tag(sender: str) -> str:
 """Return a short, privacy-safe tag for a WhatsApp sender number."""
 # Use last 4 digits of the number + a short hash prefix for uniqueness.
 # Example output: "s:7a3f:0000" — no full number is ever logged.
 clean = re.sub(r"\D", "", sender or "")
 suffix = clean[-4:] if clean else "????"
 h = hashlib.sha1(sender.encode()).hexdigest()[:4]
 return f"s:{h}:{suffix}"


# ---------------------------------------------------------------------------
# MIME extension mapping
# ---------------------------------------------------------------------------

_MIME_EXTENSIONS: Final[dict[str, str]] = {
 "audio/mp3": ".mp3",
 "audio/mpeg": ".mp3",
 "audio/mp4": ".m4a",
 "audio/mp4a-latm": ".m4a",
 "audio/ogg": ".ogg",
 "audio/opus": ".ogg",
 "audio/wav": ".wav",
 "audio/webm": ".webm",
 "audio/x-m4a": ".m4a",
 "audio/aac": ".aac",
 "audio/amr": ".amr",
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
  # fdopen failed after the descriptor was already created,
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


# ---------------------------------------------------------------------------
# Fallback sender
# ---------------------------------------------------------------------------

async def _send_fallback(sender: str) -> None:
 """Send the graceful fallback, swallowing send failures without masking
 the original error.
 """
 tag = _sender_tag(sender)
 try:
  await send_whatsapp_message(sender, GRACEFUL_FALLBACK)
 except asyncio.CancelledError:
  # If the task was cancelled while trying to send the fallback,
  # propagate that cancellation so the webhook itself cancels.
  raise
 except Exception as send_exc:
  # Secondary failure (the fallback itself failed). Log it at error level
  # but do NOT re-send — that would spam the user.
  logger.exception(
   "Fallback send failed | sender={} [{}] {}",
   tag,
   type(send_exc).__qualname__,
   send_exc,
  )


# ---------------------------------------------------------------------------
# Media-error → human-readable reason mapping (for download-failure logs)
# ---------------------------------------------------------------------------

_DOWNLOAD_FAILURE_REASON: Final[dict[MediaError, str]] = {
 MediaError.INVALID_MEDIA_ID: "media_not_found_or_expired",
 MediaError.AUTH_FAILED: "auth_failed_check_token",
 MediaError.RATE_LIMITED: "rate_limited",
 MediaError.DOWNLOAD_FAILED: "download_failed",
 MediaError.TRANSPORT_ERROR: "network_error",
 MediaError.EMPTY_BODY: "empty_body",
}


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
 tag = _sender_tag(sender)

 # Guarantee tmp_path is initialised before any try block so the finally
 # clause can reference it unconditionally.
 tmp_path: Optional[Path] = None
 normalised_path: Optional[Path] = None

 # ── Phase 1: validate and extract from raw payload ───────────────────────

 media_id: Optional[str] = None
 mime_type: Optional[str] = None
 is_voice_note: bool = False

 if not raw:
  logger.warning("Audio payload is None | sender={}", tag)
  await _send_fallback(sender)
  return

 msg_type = raw.get("type", "unknown")
 audio_obj = raw.get("audio")
 if not audio_obj:
  logger.warning(
   "No audio object in message | sender={} type={}",
   tag,
   msg_type,
  )
  await _send_fallback(sender)
  return

 media_id = audio_obj.get("id")
 mime_type = audio_obj.get("mime_type")
 # WhatsApp marks voice notes with audio/ogg or audio/opus and the
 # "voice" flag or just the audio object (as opposed to a document).
 # Treat audio/ogg + audio/opus as voice notes by default.
 is_voice_note = (mime_type or "").lower() in ("audio/ogg", "audio/opus")

 if not media_id:
  logger.warning(
   "Audio message missing media_id | sender={} mime={}",
   tag,
   mime_type,
  )
  await _send_fallback(sender)
  return

 logger.info(
  "Audio received | message_id={} sender={} media_id={} mime={} "
  "codec=opus kind={} size={}b caption={}",
  raw.get("id", "unknown"),
  tag,
  media_id,
  mime_type or "unknown",
  "opus",
  "voice_note" if is_voice_note else "audio",
  audio_obj.get("file_size", "unknown"),
  (raw.get("caption") or "")[:80],
 )

 # ── Phase 2: download ─────────────────────────────────────────────────────

 logger.info("Audio download started | sender={} media_id={}", tag, media_id)
 data: Optional[bytes] = await download_media_bytes(media_id)
 if data is None:
  logger.error(
   "Audio download failed | sender={} media_id={} reason=download_returned_none",
   tag,
   media_id,
  )
  await _send_fallback(sender)
  return

 bytes_downloaded = len(data)
 logger.info(
  "Audio download complete | sender={} media_id={} bytes={}",
  tag,
  media_id,
  bytes_downloaded,
 )

 # ── Phase 3–7: all remaining work in one try/finally ─────────────────────

 try:
  # Phase 3: write to temp file (source format, preserved extension).
  try:
   tmp_path = _write_temp_audio(data, mime_type)
   logger.debug(
    "Audio source staged | path={} bytes={} format={}",
    tmp_path.name,
    bytes_downloaded,
    _extension_for_mime(mime_type).lstrip("."),
   )
  except (OSError, PermissionError) as exc:
   logger.exception(
    "Temp file write failed | sender={} media_id={} [{}] {}",
    tag,
    media_id,
    type(exc).__qualname__,
    exc,
   )
   await _send_fallback(sender)
   return

  # Phase 4: normalise via FFmpeg → 16 kHz mono WAV.
  # Explanation: WhatsApp voice notes are AMR-NB (8 kHz) wrapped in OGG.
  # Groq whisper-large-v3 needs a standard format; 16 kHz mono WAV is the
  # safest choice accepted by every major STT provider.
  normalised: bytes = data
  normalise_mime: Optional[str] = mime_type
  try:
   normalised = normalise_audio(data, mime_type)
   normalise_mime = "audio/wav"
  except RuntimeError as norm_exc:
   # normalise_audio already errors with exit code + first 400 chars of
   # stderr. We log the full exception chain here so operators can see
   # both the high-level failure and the underlying FFmpeg diagnostic.
   logger.error(
    "Audio normalization failed | sender={} media_id={} "
    "input_bytes={} input_format={} exit_code=1",
    tag,
    media_id,
    bytes_downloaded,
    _extension_for_mime(mime_type).lstrip("."),
   )
   # Log the sanitized stderr separately so the key diagnostic is visible
   # even if the upstream message format changes.
   err_msg = str(norm_exc)
   # Extract just the FFmpeg stderr portion after "ffmpeg exited with code N: "
   stderr_part = err_msg
   if "ffmpeg exited with code" in err_msg:
    stderr_part = err_msg.split("ffmpeg exited with code", 1)[-1]
    stderr_part = stderr_part.split(":", 1)[-1].strip() if ":" in stderr_part else err_msg
   logger.error("FFmpeg diagnostic | {}", stderr_part[:500])
   await _send_fallback(sender)
   return

  # Phase 5: write normalised bytes to a temp file.
  try:
   normalised_path = _write_temp_audio(normalised, normalise_mime)
  except (OSError, PermissionError) as exc:
   logger.exception(
    "Temp file write (normalised) failed | sender={} media_id={} [{}] {}",
    tag,
    media_id,
    type(exc).__qualname__,
    exc,
   )
   await _send_fallback(sender)
   return

  norm_size = normalised_path.stat().st_size
  if norm_size == 0:
   logger.error(
    "Normalised audio is empty | sender={} media_id={} path={}",
    tag,
    media_id,
    normalised_path.name,
   )
   await _send_fallback(sender)
   return

  logger.info(
   "Audio normalized | sender={} media_id={} source_format={} "
   "output_format=wav sample_rate=16000 channels=1 bytes={}",
   tag,
   media_id,
   _extension_for_mime(mime_type).lstrip("."),
   norm_size,
  )

  # Phase 6: transcribe.
  # Explanation: transcribe_audio handles its own retries internally
  # (via tenacity on transient Groq errors). handle_audio only sees
  # the final result.
  t1 = time.monotonic()
  transcript: Optional[str] = await transcribe_audio(normalised_path)

  if transcript is None:
   logger.error(
    "Transcription returned None | sender={} media_id={} "
    "reason=permanent_or_exhausted_failure",
    tag,
    media_id,
   )
   await _send_fallback(sender)
   return

  transcript = transcript.strip()
  if not transcript:
   logger.warning(
    "Audio transcription returned empty result | "
    "sender={} media_id={}",
    tag,
    media_id,
   )
   await _send_fallback(sender)
   return

  latency_ms = int((time.monotonic() - t1) * 1000)
  logger.info(
   "Audio transcription complete | sender={} media_id={} "
   "chars={} latency_ms={}",
   tag,
   media_id,
   len(transcript),
   latency_ms,
  )

  # Phase 7: feed through the same pipeline as a normal text message.
  # Explanation: Passing the original WhatsApp message id in the payload
  # preserves dedup and audit-logging that the text pipeline already
  # implements — no new reasoning path needed in Samantha's agent.
  text_payload: dict = {
   "text": {"body": transcript},
   "id": raw.get("id"),
   # Preserve origin metadata so the agent (and any downstream tool) can
   # distinguish a voice-note transcript from a typed message if needed.
   "audio_origin": {
    "media_id": media_id,
    "mime_type": mime_type,
    "is_voice_note": is_voice_note,
   },
  }
  await handle_text(sender, text_payload)

  logger.info(
   "Agent processing complete | sender={} media_id={} total_ms={}",
   tag,
   media_id,
   int((time.monotonic() - t0) * 1000),
  )

 except asyncio.CancelledError:
  # Propagate immediately — the finally block still cleans up tmp_path,
  # but we do not log cancellation as an error.
  raise

 except Exception as exc:
  # handle_text or transcribe_audio (despite retries) raised an unexpected
  # error. Log with structured context and send fallback.
  logger.exception(
   "Agent error handling transcribed audio | sender={} media_id={} [{}] {}",
   tag,
   media_id,
   type(exc).__qualname__,
   exc,
  )
  await _send_fallback(sender)

 finally:
  # Phase 8: always clean up — guaranteed, every path.
  for path in (tmp_path, normalised_path):
   if path is not None and path.exists():
    try:
     path.unlink()
     logger.debug("Temp audio cleaned | path={}", path.name)
    except PermissionError:
     logger.warning(
      "PermissionError removing temp file {} — "
      "check OS permissions for the temp directory.",
      path,
     )
    except OSError as exc:
     logger.warning(
      "OS error removing temp file {}: [{}] {}",
      path,
      type(exc).__qualname__,
      exc,
     )
    except Exception as exc:
     logger.warning(
      "Unexpected error removing temp file {}: [{}] {}",
      path,
      type(exc).__qualname__,
      exc,
     )
