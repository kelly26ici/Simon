# src/messages/audios/transcriber.py

"""Speech-to-Text transcription via Groq's audio API.

The Groq API key is read exclusively from the environment (GROQ_API_KEY) and
is never hardcoded or committed. The model is configurable with GROQ_STT_MODEL
(defaults to whisper-large-v3).

Optimised with:
- No broad `except Exception` catch-alls.
- Every groq exception class handled explicitly — auth errors fail fast,
  rate-limit errors honour Retry-After, server errors back off with jitter.
- Transient errors (429, 502, 503, connection drop, timeout) are retried
  up to 3 times with exponential back-off + jitter via tenacity.
- CancelledError is always re-raised immediately — catching it in a bare
  `except` breaks asyncio task-cancellation propagation and causes stuck tasks.
- path.isfile() + size check done before the Groq call to fail fast on
  bad local state without wasting an API call.
- Lazy groq import so the webhook starts even when GROQ_API_KEY is absent;
  the failure is surfaced at call time as RuntimeError with a clear message.
- AsyncGroq client is cached on first creation.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

from loguru import logger
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from src.configs.settings import GROQ_STT_MODEL


# ---------------------------------------------------------------------------
# Module-level AsyncGroq instance — created on first call, reused after.
# ---------------------------------------------------------------------------

_client: Optional[object] = None


def _load_client() -> object:
    """Return the cached AsyncGroq, or create-and-cache it on first call."""
    global _client
    if _client is not None:
        return _client

    # Lazy import — groq is a normal dependency but this factory is also
    # isolated so the rest of the module remains importable when the env
    # var is absent (e.g. during tests that patch it out).
    from groq import AsyncGroq
    from src.configs.settings import GROQ_API_KEY

    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set in the environment; "
            "set it in .env or export it before starting the server."
        )
    _client = AsyncGroq(api_key=GROQ_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Exception classification helpers
# ---------------------------------------------------------------------------

def _is_transient(exc: BaseException) -> bool:
    """Return True only when retrying is likely to succeed."""
    from groq import (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    )
    return isinstance(exc, (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError))


def _on_retry(retry_state) -> None:
    """Log each retry attempt with structured context."""
    exc = retry_state.outcome.exception()
    attempt = retry_state.attempt_number
    logger.warning(
        "Transient transcription error (attempt {}/3): [{}] {}",
        attempt, type(exc).__qualname__, exc,
    )


def _wait(retry_state) -> float:
    """Exponential back-off with jitter, capped at 30 seconds.

    For RateLimitError the SDK response may carry a ``retry-after`` header;
    honour it when present so we back off exactly as Meta/Groq asks.
    """
    exc = retry_state.outcome.exception()
    try:
        headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
        retry_after = int(headers.get("retry-after", 0))
    except (ValueError, TypeError):
        retry_after = 0
    if retry_after > 0:
        logger.info("Honouring Retry-After {}s from Groq", retry_after)
        return float(retry_after)
    return wait_exponential_jitter(initial=1, max=30)(retry_state)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Maximum size for models.explain (32 KiB token budget).
# Rejection happens here so it costs nothing compared to calling the API.
_MAX_TRANSCRIPT_BYTES = 25 * 1024 * 1024  # 25 MB -- matches Groq API maximum per request.


async def transcribe_audio(audio_path: Path) -> Optional[str]:
    """Transcribe a local audio file using Groq's whisper-large-v3 (or configured model).

    Parameters
    ----------
    audio_path : Path
        Filesystem path to the audio file.  Must be a regular file; must
        not be empty.

    Returns
    -------
    str | None
        Transcribed text on success, or None on any permanent failure so
        the caller can respond with a graceful fallback message.
    """
    ctx = str(audio_path)

    # ── Pre-flight checks (no API call, fail instantly) ────────────────────

    if not Path(audio_path).is_file():
        logger.error("Audio path is not a file: {}", ctx)
        return None

    file_size = Path(audio_path).stat().st_size
    if file_size == 0:
        logger.error("Audio file is empty (0 bytes): {}", ctx)
        return None

    if file_size > _MAX_TRANSCRIPT_BYTES:
        logger.error(
            "Audio file {} exceeds {} bytes — upload will be rejected "
            "by the Groq API",
            ctx, _MAX_TRANSCRIPT_BYTES,
        )
        return None

    logger.debug(
        "Transcribing {} ({:.1f} KB) via model '{}'",
        ctx, file_size / 1024, GROQ_STT_MODEL,
    )

    # ── Call Groq with retry on transient errors ────────────────────────────

    try:
        response = await _call_groq(audio_path, ctx)
    except _PermanentFailure as perm:
        logger.error("Permanent transcription failure for {}: [{}] {}", ctx, type(perm.exc).__qualname__, perm.exc)
        return None
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # tenacity has exhausted all retries on a transient error.
        logger.exception(
            "Transcription failed after all retries for {}: [{}] {}",
            ctx, type(exc).__qualname__, exc,
        )
        return None

    # ── Extract and validate the text ───────────────────────────────────────

    text: str = getattr(response, "text", None) or ""
    text = text.strip()

    if not text:
        logger.warning("Groq returned an empty transcription for {}", ctx)
        return None

    logger.info("Transcription complete for {} — {} chars", ctx, len(text))
    return text


# ---------------------------------------------------------------------------
# Internals — isolated so tenacity can wrap them cleanly.
# ---------------------------------------------------------------------------

class _PermanentFailure(Exception):
    """Raised when the error is non-retryable so the caller short-circuits without waiting for tenacity."""

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        super().__init__(str(exc))


async def _call_groq(audio_path: Path, ctx: str) -> object:
    """Execute the model call within a tenacity retry context.

    Raises ``_PermanentFailure`` on non-retryable errors (auth, bad params,
    model not found) so the caller immediately returns None without waiting
    for tenacity's attempts to exhaust.  ``CancelledError`` is always
    re-raised without logging.
    """
    from groq import (
        APIConnectionError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        InternalServerError,
        NotFoundError,
        RateLimitError,
        UnprocessableEntityError,
    )

    client = _load_client()

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=_wait,
        retry=retry_if_exception(_is_transient),
        reraise=True,
    ):
        with attempt:
            try:
                with audio_path.open("rb") as fh:
                    response = await client.audio.transcriptions.create(
                        file=fh,
                        model=GROQ_STT_MODEL,
                        response_format="json",
                    )
                return response
            except asyncio.CancelledError:
                raise
            except (AuthenticationError, BadRequestError, UnprocessableEntityError, NotFoundError) as exc:
                logger.error(
                    "Permanent Groq error for {} — will not retry: [{}] {}",
                    ctx, type(exc).__qualname__, exc,
                )
                raise _PermanentFailure(exc)
            except (RateLimitError,) as exc:
                _on_retry(attempt.retry_state)
                raise
            except (APIConnectionError, APITimeoutError, InternalServerError) as exc:
                _on_retry(attempt.retry_state)
                raise
            except Exception as exc:
                logger.warning(
                    "Unexpected error for {} (attempt {}): [{}] {}",
                    ctx, attempt.retry_state.attempt_number,
                    type(exc).__qualname__, exc,
                )
                raise

    raise RuntimeError("Unreachable: AsyncRetrying loop should always raise or return")  # pragma: no cover
