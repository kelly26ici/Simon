"""Web Chat API route for Simon agent.

Exposes Simon agent (the same AI real-estate agent that powers the WhatsApp
experience) over a simple HTTP endpoint so that external websites can embed
Simon agent as a sidebar / chat bubble.

This route reuses the full existing conversation pipeline:
  - Redis-backed per-session history (src.messages.chats.conversation)
  - Supabase write-through of every message (conversation_messages table)
  - The OpenAI-compatible Chat Completions client with the Kimi K3
    auto-failover cascade (src.services.llm.ask_llm)
  - The complete registered ToolRegistry (search_properties,
    semantic_search_properties, get_property_details, create_property,
    schedule_property_viewing, save_customer_fact, notify_owner, …)

The only difference from the WhatsApp path (handle_text) is the delivery
layer: instead of `send_whatsapp_message` (Meta Graph API), the reply is
returned as JSON so a browser-based widget can render it.
"""

from __future__ import annotations

import secrets
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from src.configs.settings import SAMANTHA_WEB_API_KEY
from src.messages.chats.conversation import append_message, get_history
from src.messages.chats.text_handler import _build_customer_context_string
from src.services.db import db
from src.services.llm import (
    LLMAuthenticationError,
    LLMError,
    LLMRateLimitError,
    LLMServiceUnavailableError,
    ask_llm,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Schemas ───────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """A single message from a web visitor."""

    session_id: Optional[str] = Field(
        default=None,
        description="Visitor session identifier. If omitted, the server generates one "
        "and returns it so the caller can persist it (e.g. in localStorage).",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="The visitor's message text.",
    )


class ChatResponse(BaseModel):
    """Simon agent's reply, returned as JSON for the browser widget."""

    reply: str
    session_id: str
    source: str = "web"


# ── Auth ──────────────────────────────────────────────────────────────

async def _require_api_key(x_api_key: Optional[str] = Header(default=None)):
    """Guard the LLM-backed endpoint against uncontrolled third-party traffic.

    When ``SAMANTHA_WEB_API_KEY`` is configured, every request must carry a
    matching ``X-API-Key`` header.  When it is left unset the endpoint is open
    (development convenience only).
    """
    if SAMANTHA_WEB_API_KEY:
        provided = x_api_key or ""
        if not provided or not secrets.compare_digest(provided, SAMANTHA_WEB_API_KEY):
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing API key.",
                headers={"WWW-Authenticate": "ApiKey"},
            )
    return True


# ── Endpoint ──────────────────────────────────────────────────────────

@router.post("/", response_model=ChatResponse)
async def web_chat(
    payload: ChatRequest,
    _: bool = Depends(_require_api_key),
):
    """Relay a visitor message to Simon agent and return its reply as JSON.

    The conversation is persisted exactly as the WhatsApp path persists it
    (Redis history + Supabase ``conversation_messages``), so a visitor who
    later messages the company on WhatsApp with the same identifier can pick
    up the same thread.  Session keys are namespaced with the ``web-`` prefix
    to avoid clashing with real phone-number keys used by WhatsApp.
    """
    session_id = (payload.session_id or f"web-{uuid.uuid4()}").strip()
    user_text = payload.message.strip()

    # 1. Persist + cache the user turn (same envelope the text handler uses)
    await append_message(session_id, "user", user_text)
    try:
        await db.save_message(
            session_id,
            "user",
            content={"role": "user", "content": [{"type": "input_text", "text": user_text}]},
            wamid=None,
            source="web",
        )
    except Exception as exc:
        logger.warning("DB save (web user) failed for {}: {}", session_id, exc)

    # 2. Rebuild context + run the SAME LLM/tool loop as the WhatsApp path
    history = await get_history(session_id)
    customer_context = await _build_customer_context_string(session_id)

    try:
        reply = await ask_llm(history, customer_context=customer_context)
    except (LLMRateLimitError, LLMAuthenticationError, LLMServiceUnavailableError, LLMError) as exc:
        logger.error("LLM error for web session {}: {}", session_id, exc)
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected LLM error for web session {}: {}", session_id, exc)
        raise HTTPException(status_code=500, detail="Simon agent is temporarily unavailable.")

    reply_text = getattr(reply, "output_text", "") or ""
    if not reply_text:
        reply_text = "I'm having trouble answering right now — please try again in a moment. 😊"

    # 3. Persist + cache the assistant turn, then return JSON (no WhatsApp send)
    await append_message(session_id, "assistant", reply_text)
    try:
        await db.save_message(
            session_id,
            "assistant",
            content={"role": "assistant", "content": [{"type": "output_text", "text": reply_text}]},
            source="web",
        )
    except Exception as exc:
        logger.warning("DB save (web assistant) failed for {}: {}", session_id, exc)

    logger.info(
        "Web chat turn | session={} msg_len={} reply_len={}",
        session_id,
        len(user_text),
        len(reply_text),
    )
    return ChatResponse(reply=reply_text, session_id=session_id)
