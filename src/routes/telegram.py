# src/routes/telegram.py

from __future__ import annotations

import os
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, Response, BackgroundTasks
from loguru import logger

from src.services.telegram import (
    save_simon_chat_id,
    get_simon_chat_id,
    send_telegram_message,
    set_telegram_webhook,
    get_telegram_webhook_info,
    get_telegram_me,
)
from src.services.db import db

router = APIRouter(tags=["telegram"])


@router.get("/telegram/webhook")
@router.get("/api/telegram/webhook")
async def telegram_webhook_health():
    """Healthcheck for the Telegram Webhook."""
    simon_id = await get_simon_chat_id()
    return {
        "status": "active",
        "service": "Samantha Telegram Webhook",
        "simon_chat_id_configured": bool(simon_id),
    }


@router.post("/telegram/webhook")
@router.post("/api/telegram/webhook")
async def telegram_webhook_receive(request: Request, background_tasks: BackgroundTasks):
    """Handles incoming updates from Telegram Bot API.

    When the owner (Simon) clicks or sends /start (or .start), this captures his
    Chat ID, saves it to the database/cache, and replies with a confirmation.
    """
    try:
        update: Dict[str, Any] = await request.json()
    except Exception as exc:
        logger.warning("Invalid JSON received on Telegram webhook: {}", exc)
        return Response(status_code=400, content="Invalid JSON")

    message = update.get("message") or update.get("edited_message")
    if not message or not isinstance(message, dict):
        return {"ok": True}

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return {"ok": True}

    from_user = message.get("from") or {}
    username = from_user.get("username")
    first_name = from_user.get("first_name", "Owner")
    text = (message.get("text") or "").strip()

    logger.info(
        "Telegram update received | chat_id={} user='{}' text='{}'",
        chat_id,
        username or first_name,
        text,
    )

    clean_cmd = text.lower()

    # 1. Start / Setup command — capture and activate owner chat ID
    if clean_cmd.startswith(("/start", ".start", "/setup", ".setup")):
        await save_simon_chat_id(
            chat_id,
            username=username,
            first_name=first_name,
        )

        welcome_msg = (
            f"👋 *Hello {first_name}!*\n\n"
            f"✅ Your Telegram Chat ID (`{chat_id}`) has been successfully connected to "
            f"*Samantha (Realtors Round Tables)*.\n\n"
            f"You will now receive:\n"
            f"• 🏠 *Instant Lead Alerts* (ready-to-buy/rent clients)\n"
            f"• 📅 *Scheduled Viewing Appointments*\n"
            f"• 📝 *Live Real Estate Conversation Summaries*\n"
            f"• 👤 *Direct Human Escalations*\n\n"
            f"Whenever Samantha finishes a customer negotiation or qualifies a hot lead, "
            f"she will send full details directly to this chat."
        )
        background_tasks.add_task(send_telegram_message, welcome_msg, chat_id=chat_id)
        return {"ok": True, "action": "owner_registered", "chat_id": chat_id}

    # 2. Status command
    if clean_cmd.startswith(("/status", ".status")):
        active_owner_id = await get_simon_chat_id()
        status_msg = (
            f"📊 *Samantha System Status*\n\n"
            f"• *Status:* Online & Operational ✅\n"
            f"• *Active Owner Chat ID:* `{active_owner_id or 'None'}`\n"
            f"• *This Chat ID:* `{chat_id}`\n"
            f"• *Company:* Realtors Round Tables (Kenya)\n"
            f"• *Website:* https://realtorsroundtables.co.ke"
        )
        background_tasks.add_task(send_telegram_message, status_msg, chat_id=chat_id)
        return {"ok": True, "action": "status_sent"}

    # 3. Fetch summary for a customer phone: /summary <phone>
    if clean_cmd.startswith(("/summary", ".summary")):
        parts = text.split()
        if len(parts) > 1:
            query_phone = parts[1].strip()
            summary = await db.get_conversation_summary(query_phone)
            if summary:
                resp_text = (
                    f"📝 *Conversation Summary for {query_phone}*\n\n"
                    f"{summary}"
                )
            else:
                resp_text = f"ℹ️ No conversation summary found for `{query_phone}`."
        else:
            resp_text = "Usage: `/summary <phone_number>` (e.g. `/summary 254701454854`)"

        background_tasks.add_task(send_telegram_message, resp_text, chat_id=chat_id)
        return {"ok": True, "action": "summary_queried"}

    # 4. Help command
    if clean_cmd.startswith(("/help", ".help")):
        help_msg = (
            f"🤖 *Samantha Owner Bot Commands*\n\n"
            f"• `/start` or `.start` — Link this Telegram account to receive leads\n"
            f"• `/status` — View system and connection status\n"
            f"• `/summary <phone>` — Fetch latest conversation summary for a client\n"
            f"• `/help` — Show this guide"
        )
        background_tasks.add_task(send_telegram_message, help_msg, chat_id=chat_id)
        return {"ok": True, "action": "help_sent"}

    return {"ok": True}


@router.post("/telegram/set-webhook")
async def telegram_set_webhook(request: Request):
    """Utility endpoint to register webhook URL with Telegram Bot API."""
    data = {}
    try:
        data = await request.json()
    except Exception:
        pass

    custom_url = data.get("url")
    success = await set_telegram_webhook(custom_url)
    return {"success": success}


@router.get("/telegram/info")
async def telegram_info():
    """Returns Telegram webhook info and bot identity."""
    webhook_info = await get_telegram_webhook_info()
    bot_me = await get_telegram_me()
    simon_id = await get_simon_chat_id()

    return {
        "webhook_info": webhook_info,
        "bot_info": bot_me,
        "simon_chat_id": simon_id,
    }
