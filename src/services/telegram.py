# src/services/telegram.py

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
import httpx
from loguru import logger

from src.configs.settings import TELEGRAM_BOT_TOKEN, SIMON_CHAT_ID
from src.core.redis import RedisStore
from src.services.db import db

# Redis / In-memory store for Telegram state
_telegram_store = RedisStore("telegram_config")
_cached_simon_chat_id: Optional[str] = None

TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_MAX_MSG_LEN = 4000  # Safe threshold below Telegram's 4096 character limit


async def get_simon_chat_id() -> Optional[str]:
    """Resolves Simon's / Owner's Telegram chat ID.

    Lookup hierarchy:
    1. In-memory cached value
    2. Redis / memory store
    3. Database bot_settings table ('SIMON_CHAT_ID')
    4. Environment variable SIMON_CHAT_ID
    """
    global _cached_simon_chat_id

    if _cached_simon_chat_id:
        return _cached_simon_chat_id

    # 2. Redis / Store
    stored = await _telegram_store.get("SIMON_CHAT_ID")
    if stored:
        _cached_simon_chat_id = str(stored)
        return _cached_simon_chat_id

    # 3. Database
    try:
        db_id = await db.get_owner_chat_id()
        if db_id:
            _cached_simon_chat_id = str(db_id)
            await _telegram_store.set("SIMON_CHAT_ID", _cached_simon_chat_id)
            return _cached_simon_chat_id
    except Exception as exc:
        logger.debug("Could not fetch SIMON_CHAT_ID from DB: {}", exc)

    # 4. Environment
    env_id = (SIMON_CHAT_ID or os.getenv("SIMON_CHAT_ID", "")).strip()
    if env_id:
        _cached_simon_chat_id = env_id
        return _cached_simon_chat_id

    return None


async def save_simon_chat_id(
    chat_id: str | int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> bool:
    """Saves and activates Simon's / Owner's Telegram chat ID across memory, cache, and database."""
    global _cached_simon_chat_id

    chat_id_str = str(chat_id).strip()
    if not chat_id_str:
        return False

    _cached_simon_chat_id = chat_id_str

    # 1. Update cache/store
    try:
        await _telegram_store.set("SIMON_CHAT_ID", chat_id_str)
    except Exception as exc:
        logger.warning("Failed to store SIMON_CHAT_ID in cache: {}", exc)

    # 2. Persist in database
    try:
        await db.save_owner_chat_id(
            chat_id_str,
            username=username,
            first_name=first_name,
        )
    except Exception as exc:
        logger.warning("Failed to persist SIMON_CHAT_ID to database: {}", exc)

    logger.success(
        "Simon / Owner Telegram Chat ID saved and active | chat_id={} username={} first_name={}",
        chat_id_str,
        username,
        first_name,
    )
    return True


def _chunk_text(text: str, max_chars: int = TELEGRAM_MAX_MSG_LEN) -> List[str]:
    """Splits a long message into coherent chunks within Telegram's character limits."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    lines = text.split("\n")
    current_chunk: List[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > max_chars:
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0

            # If a single line is absurdly long, break it by characters
            if len(line) > max_chars:
                for i in range(0, len(line), max_chars):
                    chunks.append(line[i : i + max_chars])
                continue

        current_chunk.append(line)
        current_len += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


async def send_telegram_message(
    text: str,
    chat_id: Optional[str | int] = None,
    parse_mode: Optional[str] = "Markdown",
) -> bool:
    """Sends a Telegram message to the owner (or specified chat_id) via httpx POST.

    Features:
    - Auto-resolves SIMON_CHAT_ID if chat_id is not explicitly passed.
    - Gracefully splits long messages.
    - Retries automatically without markdown parse_mode if formatting syntax fails.
    - Never raises unhandled exceptions to prevent disrupting caller flows.
    """
    token = (TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    if not token:
        logger.warning(
            "Telegram notification skipped: TELEGRAM_BOT_TOKEN is not set in environment."
        )
        return False

    target_chat_id = str(chat_id) if chat_id else await get_simon_chat_id()
    if not target_chat_id:
        logger.warning(
            "Telegram notification skipped: SIMON_CHAT_ID is unknown. "
            "Owner needs to send /start or .start to the bot."
        )
        return False

    chunks = _chunk_text(text)
    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"

    all_succeeded = True

    async with httpx.AsyncClient(timeout=15.0) as client:
        for chunk in chunks:
            payload: Dict[str, Any] = {
                "chat_id": target_chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode

            try:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    continue

                # If Telegram rejected due to markdown parse errors, retry as plain text
                error_body = resp.text
                if parse_mode and (
                    "can't parse entities" in error_body
                    or "Bad Request: can't parse" in error_body
                    or "entity" in error_body.lower()
                ):
                    logger.debug("Telegram Markdown parse error, retrying as plain text...")
                    payload.pop("parse_mode", None)
                    fallback_resp = await client.post(url, json=payload)
                    if fallback_resp.status_code == 200:
                        continue
                    logger.error(
                        "Telegram sendMessage fallback failed [status={}]: {}",
                        fallback_resp.status_code,
                        fallback_resp.text,
                    )
                    all_succeeded = False
                else:
                    logger.error(
                        "Telegram sendMessage failed [status={}]: {}",
                        resp.status_code,
                        resp.text,
                    )
                    all_succeeded = False

            except Exception as exc:
                logger.exception("HTTP error sending Telegram message to {}: {}", target_chat_id, exc)
                all_succeeded = False

    if all_succeeded:
        logger.success(
            "Telegram message(s) sent successfully | chat_id={} chunks={}",
            target_chat_id,
            len(chunks),
        )
    return all_succeeded


async def set_telegram_webhook(webhook_url: Optional[str] = None) -> bool:
    """Configures the Telegram bot webhook to point to our backend."""
    token = (TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    if not token:
        logger.warning("Cannot set Telegram webhook: TELEGRAM_BOT_TOKEN is missing.")
        return False

    url = f"{TELEGRAM_API_BASE}/bot{token}/setWebhook"
    target_url = webhook_url or f"{os.getenv('RENDER_BASE_URL', '').rstrip('/')}/telegram/webhook"

    if not target_url or not target_url.startswith("https://"):
        logger.warning("Cannot set Telegram webhook: URL must start with https://, got '{}'", target_url)
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"url": target_url})
            if resp.status_code == 200 and resp.json().get("ok"):
                logger.success("Telegram webhook registered successfully: {}", target_url)
                return True
            logger.error("Failed to register Telegram webhook: [status={}] {}", resp.status_code, resp.text)
            return False
    except Exception as exc:
        logger.exception("Error setting Telegram webhook: {}", exc)
        return False


async def get_telegram_webhook_info() -> Dict[str, Any]:
    """Retrieves current Telegram webhook registration status."""
    token = (TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN is missing."}

    url = f"{TELEGRAM_API_BASE}/bot{token}/getWebhookInfo"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception as exc:
        logger.exception("Error getting Telegram webhook info: {}", exc)
        return {"ok": False, "error": str(exc)}


async def get_telegram_me() -> Dict[str, Any]:
    """Tests bot token authentication and returns bot details."""
    token = (TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN is missing."}

    url = f"{TELEGRAM_API_BASE}/bot{token}/getMe"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception as exc:
        logger.exception("Error getting Telegram getMe: {}", exc)
        return {"ok": False, "error": str(exc)}
