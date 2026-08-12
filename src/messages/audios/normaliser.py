# src/messages/audios/normaliser.py

"""Normalise any incoming audio bytes into a 16 kHz mono WAV before STT.

Why this module exists
----------------------
WhatsApp voice notes are not standard OGG-Opus streams. They are
AMR-NB (narrow-band, 8 kHz) or AMR-WB (wide-band, ~16 kHz) samples
wrapped in an OGG container with a .ogg filename. Groq's
whisper-large-v3 endpoint only accepts common media types
(flac / mp3 / mpeg / mpga / m4a / ogg / opus / wav / webm)
and is finicky about sample rate — an 8 kHz AMR payload will be
rejected with "must be of type flac mp3 ..." even though the file
looks like OGG.

ffmpeg solves this by:
1. Auto-detecting the real codec inside whatever container was uploaded.
2. Resampling to 16 kHz, mono, 16-bit PCM.
3. Rewrapping as WAV — a format every downstream STT API accepts.

The module is intentionally thin: one public function, one fallback
path, no third-party dependencies beyond the system ffmpeg binary
(which the Docker image / host already has for WhatsApp media handling).

Design
------
- Structured logging with key=value pairs at every stage.
- FFmpeg stderr is captured, sanitised, and logged separately so the
  useful diagnostic lines are visible without dumping the entire output.
- Output is validated: exists, size > 0, and starts with a valid WAV
  header ("RIFF") before being returned.
- Environment variable NORMALISER_DISABLED=true bypasses normalisation
  (useful for debugging or when the input is already in WAV format).
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from loguru import logger

# ---------------------------------------------------------------------------
# ffmpeg sanity check (fail fast on deploy if binary is missing)
# ---------------------------------------------------------------------------

def _check_ffmpeg() -> None:
 try:
  result = subprocess.run(
   ["ffmpeg", "-version"],
   capture_output=True,
   text=True,
   timeout=10,
  )
  if result.returncode != 0:
   raise RuntimeError(
    f"ffmpeg exited with code {result.returncode}: "
    f"{result.stderr[:200]}"
   )
 except FileNotFoundError:
  raise RuntimeError(
   "ffmpeg binary not found on PATH. "
   "Install it (apt-get install ffmpeg / brew install ffmpeg) "
   "or set NORMALISER_DISABLED=true to skip normalisation."
  )
 except subprocess.TimeoutExpired:
  raise RuntimeError("ffmpeg -version timed out after 10 s — binary may be hung")


# Run the check at import time so failures surface during app startup
# rather than on first inbound voice note.
_check_ffmpeg()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# 16 kHz mono 16-bit PCM — the "safe" format for every major STT API.
# Note: we intentionally do NOT pass -sample_fmt. Different ffmpeg builds
# expose the 16-bit PCM format under different names (s16, pcm_s16le, s16p).
# Omitting -sample_fmt lets ffmpeg pick the default for the WAV muxer,
# which is always 16-bit PCM — universally compatible and smaller output.
_TARGET_SAMPLE_RATE = 16_000
_TARGET_CHANNELS = 1

# Regex to pull just the useful last few lines from ffmpeg's verbose stderr.
# ffmpeg typically prints "Stream #0:0: ..." then "Output #0, wav, ..."
# followed by the actual error. We keep the last 3 non-empty lines.
_FFMPEC_STDERR_LINES_RE = re.compile(r"^(.*\S.*)$", re.MULTILINE)


def _sanitise_ffmpeg_stderr(stderr: str) -> str:
 """Extract the useful diagnostic tail from ffmpeg's verbose stderr.

 ffmpeg's stderr is a mix of progress output, stream mapping, and the
 actual error. The last few non-empty lines usually contain exactly
 what failed (e.g. "Invalid data" or "Encoder ... not found").
 """
 lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
 tail = lines[-3:] if len(lines) > 3 else lines
 return " | ".join(tail)


def _validate_wav_header(path: Path) -> Optional[str]:
 """Return None if the file starts with a valid WAV RIFF header, else a
 short diagnostic string."""
 try:
  with path.open("rb") as fh:
   header = fh.read(12)
  if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
   return None
  return f"invalid_wav_header: {header[:12]!r}"
 except OSError as exc:
  return f"read_error: {exc}"


def normalise_audio(
 source_bytes: bytes,
 source_mime: Optional[str] = None,
 *,
 timeout_s: float = 30,
 ) -> bytes:
 """Return WAV bytes with a guaranteed 16 kHz / mono / 16-bit spec.

 Parameters
 ----------
 source_bytes:
  Raw audio data as downloaded from WhatsApp.
 source_mime:
  MIME type reported by WhatsApp (e.g. ``audio/ogg``). Used for
  structured logging only — ffmpeg auto-detects the format.
 timeout_s:
  Maximum wall-clock time for the ffmpeg subprocess. Default 30 s
  covers even large voice notes comfortably.

 Returns
 -------
 bytes
  WAV-encoded PCM at 16 kHz / mono / 16-bit.

 Raises
 ------
 RuntimeError
  If ffmpeg fails (bad input, codec unsupported, timeout, …).
  The error message contains a sanitised ffmpeg stderr tail so the
  caller can log it as a structured diagnostic.
 """
 disabled = os.environ.get("NORMALISER_DISABLED", "").lower() in ("1", "true", "yes")
 if disabled:
  logger.debug(
   "Audio normalisation disabled via NORMALISER_DISABLED — "
   "passing through raw bytes ({} bytes, mime={})",
   len(source_bytes),
   source_mime,
  )
  return source_bytes

 # Derive a useful suffix for the temp input file so the filename
 # reflects the real format (e.g. .ogg or .amr) rather than generic .input.
 ext_map = {
  "audio/ogg": ".ogg",
  "audio/opus": ".ogg",
  "audio/mpeg": ".mp3",
  "audio/mp3": ".mp3",
  "audio/amr": ".amr",
  "audio/mp4": ".m4a",
  "audio/mp4a-latm": ".m4a",
  "audio/wav": ".wav",
  "audio/webm": ".webm",
  "audio/aac": ".aac",
  "audio/x-m4a": ".m4a",
 }
 src_ext = ext_map.get((source_mime or "").lower(), ".audio")

 tmp_in: Optional[Path] = None
 tmp_out: Optional[Path] = None
 try:
  fd_in, tmp_in_path = tempfile.mkstemp(suffix=src_ext)
  fd_out, tmp_out_path = tempfile.mkstemp(suffix=".wav")
  try:
   with os.fdopen(fd_in, "wb") as fh:
    fh.write(source_bytes)
  except OSError:
   try:
    os.close(fd_in)
   except OSError:
    pass
   raise
  try:
   os.close(fd_out)
  except OSError:
   pass

  tmp_in = Path(tmp_in_path)
  tmp_out = Path(tmp_out_path)

  logger.debug(
   "Normalising audio | mime={} size_kb={:.1f} input={}",
   source_mime,
   len(source_bytes) / 1024,
   tmp_in.name,
  )

  cmd = [
   "ffmpeg",
   "-hide_banner",
   "-loglevel", "error",
   "-i", str(tmp_in),
   "-ac", str(_TARGET_CHANNELS),
   "-ar", str(_TARGET_SAMPLE_RATE),
   "-y",
   str(tmp_out),
  ]
  result = subprocess.run(
   cmd,
   capture_output=True,
   text=True,
   timeout=timeout_s,
  )
  if result.returncode != 0:
   stderr = result.stderr.strip()
   diagnostic = _sanitise_ffmpeg_stderr(stderr)
   logger.error(
    "FFmpeg failed | mime={} input_bytes={} exit_code={} stderr={}",
    source_mime,
    len(source_bytes),
    result.returncode,
    diagnostic,
   )
   raise RuntimeError(
    f"ffmpeg exited with code {result.returncode}: {diagnostic}"
   )

  if not tmp_out.exists():
   logger.error(
    "FFmpeg produced no output | input={} output_path={}",
    tmp_in.name,
    tmp_out,
   )
   raise RuntimeError("ffmpeg produced no output file")

  output_bytes = tmp_out.read_bytes()
  if not output_bytes:
   logger.error("FFmpeg output is empty | input={}", tmp_in.name)
   raise RuntimeError("ffmpeg produced an empty output file")

  wav_err = _validate_wav_header(tmp_out)
  if wav_err:
   logger.error("Normalised output has invalid WAV header | {}", wav_err)
   raise RuntimeError(f"normalised output is not a valid WAV: {wav_err}")

  logger.debug(
   "Normalisation complete | output_bytes={:.1f}KB format=wav "
   "sample_rate=16000 channels=1",
   len(output_bytes) / 1024,
  )
  return output_bytes

 except subprocess.TimeoutExpired:
  logger.error(
   "FFmpeg normalisation timed out after {}s for mime={}",
   timeout_s,
   source_mime,
  )
  # Clean up any partially-created output before raising.
  raise RuntimeError(f"ffmpeg timed out after {timeout_s}s")
 except OSError as exc:
  logger.exception(
   "OS error during audio normalisation | mime={} [{}] {}",
   source_mime,
   type(exc).__qualname__,
   exc,
  )
  raise RuntimeError(f"OS error during normalisation: {exc}")
 finally:
  for p in (tmp_in, tmp_out):
   if p is not None:
    try:
     p.unlink(missing_ok=True)
    except OSError:
     pass
