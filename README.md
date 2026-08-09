# Samantha — WhatsApp Real-Estate Agent

Samantha is an intelligent WhatsApp bot for real-estate agencies, built with **FastAPI** and the **WhatsApp Cloud API**. It uses **OpenRouter** (Responses API with tool calling) to understand natural-language queries, search properties semantically via **Qdrant**, filter by structured criteria via **Supabase**, and handle payments via **M-Pesa**.

---

## Architecture Overview

```
WhatsApp User
    │
    ▼
POST /webhook  ──►  verify_signature()  ──►  parse_incoming()
                                                 │
                                                 ▼
                                            dispatch()
                                            ┌───┴───┐
                                            │       │
                                       text msg   other types
                                            │   (audio, image,
                                            ▼    document, etc.)
                                     handle_text()
                                            │
                                            ▼
                                     get_history()
                                            │
                                            ▼
                                     ask_gpt()  ──►  tool calls
                                            │           │
                                            ▼           ▼
                                     format_for_whatsapp()
                                            │
                                            ▼
                                     send_whatsapp_message()
                                            │
                                            ▼
                                   WhatsApp Cloud API
```

### Key Components

| Layer | File | Responsibility |
|-------|------|----------------|
| **Webhook** | [`src/routes/webhook.py`](src/routes/webhook.py) | GET/POST `/webhook` — verification & message receipt |
| **Validation** | [`src/messages/validator.py`](src/messages/validator.py) | SHA-256 signature verification via `META_APP_SECRET` |
| **Parsing** | [`src/messages/parser.py`](src/messages/parser.py) | Extracts sender, message type, and content from raw payload |
| **Routing** | [`src/messages/router.py`](src/messages/router.py) | Dispatches to the correct handler by message type |
| **Text Handler** | [`src/messages/chats/text_handler.py`](src/messages/chats/text_handler.py) | Orchestrates conversation history + LLM call for text messages |
| **Conversation** | [`src/messages/chats/conversation.py`](src/messages/conversation.py) | Redis-backed per-customer history with deduplication |
| **LLM** | [`src/services/llm.py`](src/services/llm.py) | OpenRouter Responses API with tool-calling loop |
| **Formatter** | [`src/messages/formatter.py`](src/messages/formatter.py) | **Markdown → WhatsApp** conversion & message splitting |
| **Sender** | [`src/messages/sender.py`](src/messages/sender.py) | HTTP delivery to WhatsApp Cloud API with retry logic |
| **Tool Registry** | [`src/tools/registry.py`](src/tools/registry.py) | Registers, validates, and executes LLM tool calls |
| **DB** | [`src/services/db.py`](src/services/db.py) | Supabase client for properties, customers, payments |
| **Redis** | [`src/core/redis.py`](src/core/redis.py) | Conversation history store with circuit-breaker & in-memory fallback |
| **HTTP Client** | [`src/clients/httpx_client.py`](src/clients/httpx_client.py) | Shared `httpx.AsyncClient` singleton with retry transport |

---

## WhatsApp Formatting Layer

The formatting layer is the **single choke-point** for all outgoing messages. It sits between the LLM output and the WhatsApp Cloud API, converting Markdown into WhatsApp-compatible formatting.

### How It Works

1. **LLM returns Markdown** — the model is prompted to respond in Markdown
2. **`format_for_whatsapp()`** is called in [`src/messages/sender.py`](src/messages/sender.py:92) — every outgoing message passes through this function
3. **Block parsing** — the text is split into semantic blocks (code blocks, tables, headings, blockquotes, lists, horizontal rules, paragraphs)
4. **Inline conversion** — each block's content is scanned for Markdown syntax and converted to WhatsApp equivalents
5. **Message splitting** — if the result exceeds 4096 characters, it's split at paragraph boundaries with `"1/N"` prefixes

### Markdown → WhatsApp Mapping

| Markdown | WhatsApp | Example |
|----------|----------|---------|
| `**bold**` / `__bold__` | `*bold*` | `**hello**` → `*hello*` |
| `*italic*` / `_italic_` | `_italic_` | `*hello*` → `_hello_` |
| `~~strikethrough~~` | `~strikethrough~` | `~~oops~~` → `~oops~` |
| `` `code` `` | `` `code` `` (preserved) | `` `var x = 1` `` → `` `var x = 1` `` |
| ` ``` ` code blocks | ` ``` ` (preserved) | Multi-line code kept verbatim |
| `# Heading` | `*Heading*` (bold) | `# Welcome` → `*Welcome*` |
| `[text](url)` | `text (url)` | `[Google](https://google.com)` → `Google (https://google.com)` |
| `![alt](url)` | Removed | Images are silently stripped |
| `> quote` | `_quote_` (italic) | `> Note:` → `_Note:_` |
| `---` | `──────────` | Horizontal rule → line of dashes |
| Tables | Unicode grid | See below |

### Table Conversion

Markdown tables are converted to a readable text grid using Unicode box-drawing characters:

```
┌──────────┬──────────────┬────────┐
│ Property │ Location     │ Price  │
├──────────┼──────────────┼────────┤
│ Apt 4B   │ Westlands    │ 15M    │
│ Villa 12 │ Karen        │ 45M    │
└──────────┴──────────────┴────────┘
```

### Message Splitting

WhatsApp Cloud API has a **4096-character limit** per message. The formatter:

- Splits at **paragraph boundaries** (double newlines)
- Never breaks inside: code blocks, URLs, lists, tables, blockquotes
- Prefixes each part with `"1/N"`, `"2/N"`, etc.
- Falls back to hard split at the character limit if a single block exceeds it

### Configuration

Set these in your `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `WHATSAPP_MAX_MESSAGE_LENGTH` | `4096` | Max characters per message (WhatsApp limit) |
| `WHATSAPP_TABLE_MODE` | `text` | `"text"` for grid, `"image"` for rendered image |
| `WHATSAPP_FORMAT_DEBUG` | `false` | Log debug info about each transformation |

### Integration Point

The formatter is integrated as a **choke-point** in [`src/messages/sender.py`](src/messages/sender.py:92):

```python
async def send_whatsapp_message(to: str, text: str) -> None:
    """Formats text via the WhatsApp formatting layer, then sends each part."""
    messages = format_for_whatsapp(text)
    for msg in messages:
        await _send_single_message(to, msg)
```

Every caller that needs to send a message uses `send_whatsapp_message()`, so formatting is applied automatically and consistently.

---

## Project Structure

```
src/
├── main.py                  # FastAPI app entry point
├── uptime.py                # Keep-alive ping lifespan
├── clients/
│   ├── httpx_client.py      # Shared HTTP client singleton
│   └── supabase_client.py   # Supabase client init
├── configs/
│   ├── settings.py          # Environment variables & configuration
│   ├── constants.py         # App-wide constants
│   └── prompts.py           # LLM system prompts
├── core/
│   └── redis.py             # Redis store with circuit breaker
├── messages/
│   ├── formatter.py         # WhatsApp formatting layer (Markdown → WhatsApp)
│   ├── sender.py            # WhatsApp Cloud API message delivery
│   ├── parser.py            # Incoming webhook payload parser
│   ├── router.py            # Message type dispatcher
│   ├── validator.py         # Webhook signature verification
│   ├── webhook.py           # Webhook event pipeline
│   ├── downloader.py        # Media downloader
│   ├── chats/
│   │   ├── text_handler.py  # Text message handler (LLM orchestration)
│   │   ├── conversation.py  # Redis-backed conversation history
│   │   └── command_handler.py
│   ├── audios/              # Audio transcription & TTS
│   ├── documents/           # Document processing
│   ├── images/              # Image analysis
│   ├── interactions/        # Buttons, lists, flows
│   ├── reactions/           # Emoji reactions
│   └── videos/              # Video processing
├── routes/
│   └── webhook.py           # Webhook GET/POST endpoints
├── services/
│   ├── llm.py               # OpenRouter LLM integration
│   └── db.py                # Supabase database client
└── tools/
    ├── registry.py          # Tool registration & execution
    ├── embeddings.py        # Cloudflare Workers AI embeddings
    ├── qdrant.py            # Qdrant collection management
    ├── tavily.py            # Web search tool
    ├── schedule_meeting.py  # Meeting scheduling tool
    ├── mpesa_agent.py       # M-Pesa agent tool
    ├── memory/              # Customer memory tools
    ├── mpesa/               # M-Pesa STK push, C2B, webhooks
    └── properties/          # Property search, semantic search, comparison
```

---

## Running the Project

### Prerequisites

- Python 3.11+
- Redis (optional — falls back to in-memory store)
- A [Meta WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api) setup
- An [OpenRouter](https://openrouter.ai/) API key
- A [Qdrant](https://qdrant.tech/) cluster
- A [Supabase](https://supabase.com/) project
- [Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/) API token (for embeddings)

### Setup

```bash
# Clone and enter the project
git clone <repo-url>
cd Samantha

# Create virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv sync

# Copy and fill in environment variables
cp .env.example .env
```

### Running

```bash
# Start the server
uv run uvicorn src.main:app --reload

# Or use the Makefile
make dev
```

### Testing

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run only formatter tests
uv run pytest tests/test_formatter.py -v

# Run only splitter/table tests
uv run pytest tests/test_formatter_splitter.py -v
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key for LLM |
| `META_ACCESS_TOKEN` | Yes | WhatsApp Cloud API access token |
| `META_PHONE_NUMBER_ID` | Yes | WhatsApp Business phone number ID |
| `META_APP_SECRET` | Yes | App secret for webhook signature verification |
| `META_VERIFY_TOKEN` | Yes | Webhook verification token |
| `QDRANT_URL` | Yes | Qdrant cluster URL |
| `QDRANT_API_KEY` | Yes | Qdrant API key |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase service role key |
| `CLOUDFLARE_ACCOUNT_ID` | Yes | Cloudflare account ID (embeddings) |
| `CLOUDFLARE_API_TOKEN` | Yes | Cloudflare API token (embeddings) |
| `TAVILY_API_KEY` | No | Web search tool |
| `REDIS_URL` | No | Redis connection string (falls back to in-memory) |
| `CONSUMER_KEY` | No | M-Pesa consumer key |
| `CONSUMER_SECRET` | No | M-Pesa consumer secret |
| `WHATSAPP_MAX_MESSAGE_LENGTH` | No | Max chars per message (default: 4096) |
| `WHATSAPP_TABLE_MODE` | No | Table rendering mode (default: text) |
| `WHATSAPP_FORMAT_DEBUG` | No | Enable formatter debug logging |

---

## License

Proprietary — all rights reserved.
