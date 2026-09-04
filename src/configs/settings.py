# src/configs/settings.py

import os
from dotenv import load_dotenv

#======================================================
#                      BODY
#======================================================


load_dotenv(override=True)


#======================================================
#                      LLMS
#======================================================


GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Speech-to-Text model used by the audio transcriber (Groq).
# Configurable via environment, defaults to whisper-large-v3.
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

_raw_nvidia_key = os.getenv("NVIDIA_API_KEY")
# If GEMINI_API_KEY holds an nvapi-* key and NVIDIA_API_KEY is empty/invalid, fallback automatically
if not _raw_nvidia_key and GEMINI_API_KEY and GEMINI_API_KEY.startswith("nvapi-"):
    NVIDIA_API_KEY = GEMINI_API_KEY
else:
    NVIDIA_API_KEY = _raw_nvidia_key

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Poolside AI — OpenAI-compatible inference API for Poolside's Laguna models.
# Base URL: https://inference.poolside.ai/v1 (Poolside-hosted inference)
POOLSIDE_API_KEY = os.getenv("POOLSIDE_API_KEY", "")
POOLSIDE_BASE_URL = os.getenv("POOLSIDE_BASE_URL", "https://inference.poolside.ai/v1")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_TEMPERATURE = os.getenv("LLM_TEMPERATURE", "0.7")
LLM_RESET_COOLDOWN_SECONDS = int(os.getenv("LLM_RESET_COOLDOWN_SECONDS", "3600"))

#======================================================
#                    WHATSAPP
#======================================================


META_VERIFY_TOKEN=os.getenv("META_VERIFY_TOKEN", "")

META_APP_SECRET=os.getenv("META_APP_SECRET", "")

META_ACCESS_TOKEN=os.getenv("META_ACCESS_TOKEN", "")

META_PHONE_NUMBER_ID=os.getenv("META_PHONE_NUMBER_ID", "")

META_GRAPH_API_VERSION=os.getenv("META_GRAPH_API_VERSION", "v23.0")

META_GRAPH_BASE_URL=os.getenv("META_GRAPH_BASE_URL", "https://graph.facebook.com")

MAX_HISTORY = int(os.getenv("MAX_HISTORY", "10"))

# How long a conversation's Redis history key lives without activity before
# automatic eviction. When a customer goes silent for this many days, the
# next message starts a fresh context window. The full history is preserved
# in Supabase conversation_messages if it was ever persisted.
CONVERSATION_TTL_SECONDS = int(os.getenv("CONVERSATION_TTL_SECONDS", str(7 * 24 * 3600)))  # 7 days


#======================================================
#                     FORMATTING
#======================================================

# Maximum characters per WhatsApp text message (WhatsApp Cloud API limit is 4096).
WHATSAPP_MAX_MESSAGE_LENGTH = int(os.getenv("WHATSAPP_MAX_MESSAGE_LENGTH", "4096"))

# How to render Markdown tables in WhatsApp:
#   "text"  — convert to a plain-text aligned grid (default)
#   "image" — render as an image (requires Pillow; falls back to text if unavailable)
WHATSAPP_TABLE_MODE = os.getenv("WHATSAPP_TABLE_MODE", "text")

# When True, the formatter logs debug info about each transformation.
WHATSAPP_FORMAT_DEBUG = os.getenv("WHATSAPP_FORMAT_DEBUG", "false").lower() in ("1", "true", "yes")


#======================================================
#                     QDRANT                          #
#======================================================


QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

QDRANT_URL = os.getenv(
    "QDRANT_URL",
    "https://a0b2e76d-24c4-4b21-85c5-e073d161e431.europe-west3-0.gcp.cloud.qdrant.io",
)


#======================================================
#                     MPESA
#======================================================

MPESA_BASE_URL = "https://sandbox.safaricom.co.ke"  #I'll switch to https://api.safaricom.co.ke at go-live

CONSUMER_SECRET=os.getenv("CONSUMER_SECRET")

CONSUMER_KEY=os.getenv("CONSUMER_KEY")

PASSKEY=os.getenv("PASSKEY")

SHORTCODE=os.getenv("SHORTCODE")

CALLBACK_URL=os.getenv("CALLBACK_URL")

MPESA_WEBHOOK_SECRET = os.getenv("MPESA_WEBHOOK_SECRET")


#======================================================
#                     REDIS
#======================================================
REDIS_URL=os.getenv("REDIS_URL", "redis://localhost:6379")

#======================================================
#                     SUPABASE
#======================================================
SUPABASE_URL=os.getenv("SUPABASE_URL", "")
SUPABASE_KEY=os.getenv("SUPABASE_KEY", "")

#======================================================
#                     TOOLS
#======================================================


#TAVILY
TAVILY_API_KEY=os.getenv("TAVILY_API_KEY")


RENDER_BASE_URL=os.getenv("RENDER_BASE_URL", "https://samantha-nrev.onrender.com")

#======================================================
#                    WEB CHAT (external website widget)
#======================================================
# Optional API key that the embeddable chat widget sends as X-API-Key.
# When set, POST /api/chat requires a matching key — protects the LLM from
# abuse by arbitrary third-party sites. Share this value with website owners
# you onboard (e.g. Damantha). Leave unset only for local development.
SAMANTHA_WEB_API_KEY = os.getenv("SAMANTHA_WEB_API_KEY", "")

#======================================================
#                    TELEGRAM
#======================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
SIMON_CHAT_ID = os.getenv("SIMON_CHAT_ID", "")

