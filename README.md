# Simon — WhatsApp Real-Estate Agent

**Simon** is a FastAPI application for **Realtors Round Tables**, a Kenya-focused real-estate customer-service assistant. It receives WhatsApp Cloud API messages, keeps per-customer context, searches property listings, schedules viewings, handles selected M-Pesa flows, and can notify the owner through Telegram.

The application combines:

- WhatsApp Cloud API webhooks and message delivery
- Redis for short-lived conversation context and deduplication
- Supabase/PostgreSQL for durable application data and conversation write-through
- Qdrant plus Cloudflare Workers AI embeddings for semantic property search
- An OpenAI-compatible Chat Completions client with an **auto-shifting model cascade (starting with Kimi K3, 2.8T MoE)** and seamless in-flight failover
- Optional Tavily web search, Groq Whisper transcription, Telegram notifications, and Safaricom Daraja M-Pesa

> This README documents the behavior implemented in the repository. Some entries in the Makefile and some older helper modules are legacy utilities and are not the application entrypoint.

---

## Architecture

```text
WhatsApp Cloud API
        |
        v
GET /webhook                    POST /webhook
  verification                    |
                                  v
                    HMAC-SHA256 signature verification
                                  |
                                  v
                    parse first inbound message / WAMID
                                  |
                    Redis WAMID deduplication (1 hour)
                                  |
                                  v
                         message type router
                    +-------------+-------------+
                    |             |             |
                  text          audio       interactive
                    |             |             |
                    |       FFmpeg + Groq      |
                    |       Whisper transcript |
                    |             |             |
                    +-------------+-------------+
                                  |
                           handle_text()
                                  |
                Redis history + Supabase write-through
                                  |
                  profile and confirmed-viewing context
                                  |
                                  v
                     OpenAI-compatible Chat Completions
                                  |
                         ToolRegistry tool loop
                                  |
                    +-------------+-------------+
                    |             |             |
              Supabase        Qdrant        Telegram /
             properties      semantic       Daraja / Tavily
             and bookings     search          integrations
                                  |
                                  v
                    plain WhatsApp-safe text chunks
                                  |
                                  v
                         WhatsApp Cloud API
```

### Runtime components

| Layer | File | Responsibility |
|---|---|---|
| Application | [`src/main.py`](src/main.py) | Creates the FastAPI app and mounts WhatsApp, Telegram, M-Pesa, and uptime routes |
| Local launcher | [`main.py`](main.py) | Runs `src.main:app` on `0.0.0.0:8000` with reload and access logs disabled |
| WhatsApp routes | [`src/routes/webhook.py`](src/routes/webhook.py) | Webhook verification and inbound POST handling |
| Webhook pipeline | [`src/messages/webhook.py`](src/messages/webhook.py) | Signature validation, parsing, WAMID deduplication, dispatch, and acknowledgement |
| Validation | [`src/messages/validator.py`](src/messages/validator.py) | Verifies Meta's `X-Hub-Signature-256` header using HMAC-SHA256 |
| Parsing | [`src/messages/parser.py`](src/messages/parser.py) | Extracts the first message, sender, type, raw payload, and recipient phone-number ID |
| Message routing | [`src/messages/router.py`](src/messages/router.py) | Dispatches registered `text`, `audio`, and `interactive` handlers |
| Text handling | [`src/messages/chats/text_handler.py`](src/messages/chats/text_handler.py) | Builds customer context, calls the LLM, persists messages, and sends replies |
| Conversation cache | [`src/messages/chats/conversation.py`](src/messages/chats/conversation.py) | Stores bounded per-customer interaction history in Redis |
| Audio handling | [`src/messages/audios/`](src/messages/audios/) | Downloads, normalizes, validates, and transcribes WhatsApp voice notes |
| Interactive handling | [`src/messages/interactions/interactive_handler.py`](src/messages/interactions/interactive_handler.py) | Converts button, list, and flow replies into text conversations |
| WhatsApp sender | [`src/messages/sender.py`](src/messages/sender.py) | Sends text, typing indicators, CTAs, and quick replies through Meta's Graph API |
| Formatter | [`src/messages/formatter.py`](src/messages/formatter.py) | Converts model output to readable WhatsApp-safe text and splits long messages |
| LLM service | [`src/services/llm.py`](src/services/llm.py) | Resolves a provider and runs the Chat Completions tool-calling loop |
| Tool registry | [`src/tools/registry.py`](src/tools/registry.py) | Declares, validates, executes, serializes, and sanitizes tool calls |
| Database service | [`src/services/db.py`](src/services/db.py) | Wraps Supabase operations for profiles, properties, messages, bookings, and payments |
| Redis service | [`src/core/redis.py`](src/core/redis.py) | Namespaced Redis store with circuit breaker and in-memory fallback |
| HTTP clients | [`src/clients/httpx_client.py`](src/clients/httpx_client.py) | Event-loop-scoped shared `httpx.AsyncClient` instances and shutdown handling |
| Lifecycle | [`src/uptime.py`](src/uptime.py) | Starts keep-alive tasks and closes shared clients on shutdown |

---

## Supported WhatsApp messages

The dispatcher currently registers only these handlers:

| Message type | Handler | Behavior |
|---|---|---|
| `text` | `handle_text` | Persists the message, adds customer context, invokes the LLM, and sends the reply |
| `audio` | `handle_audio` | Downloads and transcribes the voice note, then sends the transcript through the text flow |
| `interactive` | `handle_interactive` | Supports `button_reply`, `list_reply`, and `nfm_reply` by converting them to synthetic text |

Image, document, video, reaction, and other message directories exist in the source tree, but they are not currently registered in [`src/messages/router.py`](src/messages/router.py). Unsupported message types are logged and ignored.

### Webhook behavior

1. `GET /webhook` checks `hub.mode`, `hub.verify_token`, and `hub.challenge`.
2. `POST /webhook` verifies the raw request body against `X-Hub-Signature-256`.
3. The first inbound message is parsed from the Meta payload.
4. Its WhatsApp message ID (`wamid`) is deduplicated in Redis for one hour.
5. The registered handler is called.
6. A validly signed webhook is acknowledged with HTTP 200 even if handler execution fails. This prevents Meta from repeatedly retrying work that has already reached the application.

Outside explicit local-development mode, `META_APP_SECRET` must be set. If it is missing, verification is bypassed only when `LOCAL_DEV` is `1`, `true`, or `yes`; otherwise the webhook is rejected.

---

## LLM integration

The active integration uses the OpenAI-compatible **Chat Completions** API through `AsyncOpenAI`. It is not the OpenRouter Responses API.

`ask_llm()`:

1. Adds the system prompt from [`src/configs/prompts.py`](src/configs/prompts.py).
2. Adds the current customer profile and confirmed-viewing context when available.
3. Converts Redis interaction history into Chat Completions messages.
4. Sends the registered ToolRegistry declarations.
5. Executes returned tool calls, appends tool results, and continues the loop.
6. Stops when the model returns normal text or the tool-iteration limit is reached.

Tool failures are classified, sanitized, and returned to the model as structured output where possible. API keys, tokens, passwords, passkeys, and likely secrets are redacted from logs and error details.

### Provider resolution and Model Cascade

[`resolve_llm_config()`](src/services/llm.py) resolves configuration in this order:

1. An explicit `LLM_BASE_URL` together with `LLM_API_KEY`.
2. An explicit `LLM_PROVIDER` with the corresponding configured key.
3. Automatic detection in this order:
   - NVIDIA
   - OpenRouter
   - Groq

The active NVIDIA integration uses a **dynamic, benchmark-ranked model cascade** managed by `ModelCascadeManager` in [`src/services/llm.py`](src/services/llm.py):

| Rank | Model ID | Parameter Scale | Primary Focus / Benchmark Strength |
|---|---|---|---|
| 1 | `moonshotai/kimi-k3` *(Default Primary)* | 2.8T MoE (104B active) | Frontier Tier #1 (~1500 Arena Elo, 88% MMLU-Pro, 93.5% GPQA Diamond) |
| 2 | `minimaxai/minimax-m3` | 428B MoE (23B active) | Frontier MoE (84-87% MMLU-Pro, 92% GPQA Diamond, 1M context) |
| 3 | `nvidia/nemotron-3-super-120b-a12b` | 120B Hybrid MoE | High-capacity reasoning brain (83.7% MMLU-Pro, 79.2% GPQA) |
| 4 | `meta/llama-3.2-90b-vision-instruct` | 90B Dense | Dense reasoning and multimodal capabilities |
| 5 | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | 30B Omni | Dedicated reasoning chain-of-thought & tool calling |
| 6 | `meta/muse-glimmer-30b` | 30B Dense | High agentic benchmark capability |
| 7 | `nvidia/nemotron-3.5-lightning-30b-a3b` | 30B Dense | High-throughput instruct model |
| 8 | `google/diffusiongemma-26b-a4b-it` | 26B Dense | High factual accuracy in 26B class |
| 9 | `openai/gpt-oss-20b` | 20B Dense | Conversational baseline |
| 10 | `meta/llama-3.2-11b-vision-instruct` | 11B Dense | Fast lightweight tool-execution model |
| 11 | `poolside/laguna-xs-2.1` | Small Dense | Dialogue fallback |
| 12 | `nvidia/nemotron-3-nano-30b-a3b` | 30B Nano | Emergency lightweight fallback |

#### Key Failover & Auto-Reset Behaviors:
- **In-Flight Seamless Failover:** If an active model returns an error (429 rate limit, 5xx server error, timeout, or empty response), Simon immediately hands off the request to the next candidate model in the cascade on the same turn. The user never needs to re-type.
- **1-Hour Auto-Reset Cooldown:** Whenever the model shifts down the cascade, a 1-hour timer (`LLM_RESET_COOLDOWN_SECONDS`, default 3600s) starts. Once 1 hour elapses, the active model automatically shifts back to **`moonshotai/kimi-k3`** as the top default.
- **Reasoning Sanitization:** Models producing `<think>...</think>` chain-of-thought blocks are automatically sanitized so customers receive clean, user-facing text.

---

## Registered agent tools

All tools are imported for side-effect registration in [`src/tools/__init__.py`](src/tools/__init__.py). Pydantic schemas define the JSON contract exposed to the LLM.

### Property search and comparison

| Tool | Purpose |
|---|---|
| `search_properties` | Structured Supabase search with price, location, city, property type, listing type, bedrooms, bathrooms, size, amenities, furnishing, pet-friendliness, gated-community, sorting, and pagination filters |
| `semantic_search_properties` | Natural-language search using Cloudflare embeddings and Qdrant, with optional structured filters |
| `get_property_details` | Retrieves a full listing, images/media, agent details, and customer-service contacts |
| `compare_properties` | Compares two to four property IDs and calculates value, price per square meter, size, family fit, common amenities, unique amenities, and missing IDs |
| `create_property` | Creates or updates a property listing in Supabase and immediately indexes it in Qdrant for semantic search |

Supported property types include `house`, `apartment`, `land`, `commercial`, `townhouse`, `villa`, `cottage`, `penthouse`, and `studio`. Supported listing types are `sale` and `rent`.

### Viewings and customer support

| Tool | Purpose |
|---|---|
| `schedule_property_viewing` | Creates a physical or virtual viewing in `scheduled_viewings`, optionally linked to a property |
| `get_my_scheduled_viewings` | Lists a customer's upcoming and past viewings |
| `cancel_property_viewing` | Cancels a viewing after checking the viewing ID and customer phone |
| `get_support_contact` | Returns Simon's phone, WhatsApp link, website, and an optional listing-agent contact |

### Customer memory and conversation history

| Tool | Purpose |
|---|---|
| `save_customer_fact` | Saves a named fact such as a preferred name, budget, area, bedroom requirement, or move-in constraint |
| `get_customer_preferences` | Retrieves the saved customer profile and metadata |
| `update_conversation_summary` | Replaces the current full conversation summary in Supabase |
| `notify_owner` | Sends a Telegram alert enriched with the latest conversation summary |
| `check_payment_history` | Checks whether the customer has successful past M-Pesa transactions |
| `search_past_conversations` | Retrieves bounded, paginated historical messages from durable storage |

Unknown customer fact fields are stored in the `customer_profiles.metadata` JSONB column. The prompt asks the model to refresh conversation summaries after every three to four meaningful exchanges and to alert the owner for bookings, hot leads, human escalation, and meaningful negotiations.

### Finance and web search

| Tool | Purpose |
|---|---|
| `calculate_mortgage` | Calculates deposit, loan principal, estimated monthly repayment, interest, acquisition costs, upfront cash, and a gross-income guideline |
| `web_search` | Calls Tavily for current general or news information, with basic or advanced search and optional synthesized answers |

Mortgage calculations are intentionally restricted to explicit customer requests. The calculator uses KES, a default 20% deposit, a default 13.5% annual rate, and a default 20-year term; these are estimates, not lending approvals.

### M-Pesa tools

| Tool | Purpose |
|---|---|
| `send_stk_push` | Starts a Safaricom Daraja STK Push and records the pending transaction in Redis |
| `check_transaction_status` | Queries or resolves an STK transaction and reports `pending`, `success`, `failed`, or `cancelled` |

The internal Daraja client is not exposed directly to the LLM. The LLM sees only the validated Pydantic tool wrappers.

---

## Property data and semantic search

The property service stores structured listings in Supabase and indexes searchable text in Qdrant.

- Qdrant collection: `properties`
- Vector size: `1024`
- Distance: cosine similarity
- Embedding model: Cloudflare Workers AI `@cf/qwen/qwen3-embedding-0.6b`
- Embedding batches: up to 20 texts
- Qdrant payload indexes: `price`, `bedrooms`, `city`, `location`, `property_type`, `listing_type`, and `status`

[`src/tools/properties/__init__.py`](src/tools/properties/__init__.py) builds rich listing text, creates the collection when needed, indexes individual or all available properties, and applies Qdrant filters before semantic search.

There are two data paths:

- [`src/data/seed_properties.py`](src/data/seed_properties.py) contains a curated dataset covering Nairobi, the coast, Kangundo Road, and other Kenyan locations.
- [`src/data/ingest_properties.py`](src/data/ingest_properties.py) normalizes larger scraped CSV datasets, generates descriptions and image URLs, and adds a dedicated Kangundo Road dataset.

---

## Persistence and conversation state

### Redis

Redis is used for fast, short-lived state:

- Conversation history uses the `history` key prefix.
- Seen WhatsApp message IDs use the `seen_msg` prefix.
- M-Pesa pending transaction state and owner-chat state also use Redis-backed stores.
- History is capped by `MAX_HISTORY` entries, default `10`.
- History keys expire after `CONVERSATION_TTL_SECONDS`, default `604800` seconds (seven days).
- Redis operations use a circuit breaker with a 60-second cooldown.
- When Redis is unavailable, each `RedisStore` instance falls back to an instance-local in-memory dictionary. This keeps the process usable, but it is not shared across workers and is lost on restart.

### Supabase/PostgreSQL

Supabase is the durable store for:

- Properties and property metadata
- Customer profiles and free-form customer metadata
- Scheduled viewings
- M-Pesa transactions
- Conversation summaries
- Conversation messages
- Bot settings, including the owner Telegram chat ID

The text handler writes inbound and assistant messages through to `conversation_messages` while also maintaining the Redis context window. Inbound messages use the unique `wamid` column for database-level idempotency; assistant/system messages may have a null `wamid`.

`search_past_conversations` reads from this durable store with bounded pagination. There is currently no application deletion job for `conversation_messages`, so durable message retention is not the same as the seven-day Redis cache retention. Review [`PRIVACY_POLICY.md`](PRIVACY_POLICY.md) before production use and make its retention statement match the actual deployment policy.

---

## Outgoing WhatsApp formatting

Every normal text response passes through [`format_for_whatsapp()`](src/messages/formatter.py) in [`src/messages/sender.py`](src/messages/sender.py).

The formatter is a readability and transport layer. It does **not** convert Markdown into WhatsApp `*bold*`, `_italic_`, or `~strikethrough~` markup, and it does not render Unicode box-drawing tables.

Current behavior includes:

- Headings become uppercase text.
- Bold, italic, and strikethrough markers are removed.
- Images are removed.
- Links become `text (url)`.
- Blockquotes keep their `> ` prefix.
- Lists remain readable as plain `-` or numbered lines.
- Code blocks are rendered as an indented `Code:` section.
- Tables are summarized as simple property/detail lines rather than a grid.
- Long messages are split at block and paragraph boundaries where possible.
- Multiple chunks receive numeric prefixes.
- A hard split is used when an individual block cannot fit within the configured limit.

Relevant settings:

| Variable | Default | Description |
|---|---:|---|
| `WHATSAPP_MAX_MESSAGE_LENGTH` | `4096` | Maximum outgoing text length per WhatsApp message |
| `WHATSAPP_TABLE_MODE` | `text` | Retained formatter setting; current table output is plain readable text |
| `WHATSAPP_FORMAT_DEBUG` | `false` | Enables formatter diagnostics |

The sender also supports typing indicators, interactive CTA messages, and quick replies. Interactive send failures fall back to text where implemented.

---

## Audio messages

Voice notes follow this pipeline:

1. Extract the WhatsApp media ID and MIME type.
2. Resolve the media URL through Meta's two-step media API.
3. Download the original bytes into a temporary file.
4. Normalize the audio with FFmpeg to 16 kHz, mono WAV.
5. Validate the RIFF/WAVE output.
6. Transcribe with Groq Whisper (`GROQ_STT_MODEL`, default `whisper-large-v3`).
7. Build a synthetic text message from the transcript.
8. Reuse `handle_text()` so the transcript receives the same tools, memory, persistence, and response behavior as typed text.
9. Remove temporary files in a `finally` block.

If processing fails, the customer receives a retry message asking them to resend the voice note or type the request. Logs use a privacy-safe short sender tag rather than exposing the raw phone number. FFmpeg is required unless audio normalization is explicitly disabled with `NORMALISER_DISABLED=true`.

---

## Telegram owner integration

Telegram is used for owner alerts and owner-side status checks.

### Routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/telegram/webhook` | Telegram webhook health endpoint |
| `POST` | `/telegram/webhook` | Receives Telegram updates |
| `GET` | `/api/telegram/webhook` | Compatibility health endpoint |
| `POST` | `/api/telegram/webhook` | Compatibility receive endpoint |
| `POST` | `/telegram/set-webhook` | Registers the Telegram webhook with the Bot API |
| `GET` | `/telegram/info` | Returns Telegram bot/webhook information |

Supported owner commands include `/start` (or `.start`), `/setup` (or `.setup`), `/status`, `/summary <phone>`, and `/help`.

`/start` captures the owner's chat ID and persists it in memory, Redis, and Supabase. Notification lookup uses this order:

1. In-memory cache
2. Redis/memory store
3. Supabase `bot_settings`
4. `SIMON_CHAT_ID`

Telegram messages are split below Telegram's 4096-character limit. If Markdown parsing fails, the sender retries as plain text.

---

## M-Pesa and Daraja

The application uses the Safaricom Daraja **sandbox** by default (`MPESA_BASE_URL` is currently hardcoded to the sandbox URL in settings).

Implemented capabilities:

- OAuth client-credentials token generation with caching
- STK Push
- STK status query
- C2B URL registration
- Validation and confirmation callbacks
- Redis deduplication of callback work
- Best-effort persistence of successful transactions to Supabase

The STK state lifecycle exposed to the model is `pending`, `success`, `failed`, or `cancelled`. A newly submitted push remains `pending` until a callback or direct status query establishes a definitive result. STK request timeouts are not blindly retried because Safaricom may have accepted the request even when the response was delayed.

### Callback routes

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/mpesa/callback/{secret}` | STK callback |
| `POST` | `/mpesa/c2b/validation/{secret}` | C2B validation callback |
| `POST` | `/mpesa/c2b/confirmation/{secret}` | C2B confirmation callback |

The secret path segment is an application-level guard, not a Safaricom cryptographic signature. Daraja callbacks are not cryptographically signed by this implementation. For real-money deployments, also restrict access at the network or reverse-proxy layer to Safaricom's documented source ranges and keep the callback secret private.

The client generates STK timestamps using `Africa/Nairobi` time, validates Kenyan phone numbers in `254XXXXXXXXX` form, and avoids claiming payment success until a definitive result is available.

---

## HTTP API

The application entrypoint is `src.main:app`.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/uptime` | Returns a simple service status message |
| `GET` | `/webhook` | Meta webhook verification |
| `POST` | `/webhook` | Meta inbound WhatsApp webhook |
| `GET`/`POST` | `/telegram/webhook` | Telegram health and update receiver |
| `GET`/`POST` | `/api/telegram/webhook` | Telegram compatibility aliases |
| `POST` | `/telegram/set-webhook` | Configure Telegram webhook |
| `GET` | `/telegram/info` | Inspect Telegram bot/webhook state |
| `POST` | `/mpesa/callback/{secret}` | Daraja STK callback |
| `POST` | `/mpesa/c2b/validation/{secret}` | Daraja C2B validation |
| `POST` | `/mpesa/c2b/confirmation/{secret}` | Daraja C2B confirmation |
| `GET` | `/api/properties/` | Search/list available properties with filters and pagination |
| `GET` | `/api/properties/{id}` | Retrieve full details for a single property |
| `POST` | `/api/properties/` | Create or update a property listing (requires HTTP Basic auth) |
| `DELETE` | `/api/properties/{id}` | Delete a property from Supabase and Qdrant (requires HTTP Basic auth) |
| `GET` | `/api/properties/total` | Count of matching available properties |

---

## Project structure

```text
.
├── main.py                         # Local uvicorn launcher
├── pyproject.toml                  # Package metadata and dependencies
├── uv.lock                         # Locked Python dependencies
├── .env.example                    # Environment variable template
├── SQl/
│   └── schema.sql                  # PostgreSQL/Supabase schema
├── scripts/
│   ├── check_db.py                 # Database diagnostics
│   ├── keep_alive.py               # Standalone Supabase/Qdrant pings
│   ├── migrate.py                  # Applies SQl/schema.sql
│   ├── seed_database.py            # Full ingest + seed + Qdrant indexing
│   └── seed_properties.py          # Curated sample seed + indexing
├── src/
│   ├── main.py                     # FastAPI application
│   ├── cli.py                      # Status, seed, sync, search, and chat CLI
│   ├── uptime.py                   # Application lifecycle keep-alive tasks
│   ├── clients/
│   │   └── httpx_client.py         # Shared async HTTP clients
│   ├── configs/
│   │   ├── constants.py            # Model constants
│   │   ├── prompts.py              # Assistant system prompt
│   │   └── settings.py             # Environment-backed settings
│   ├── core/
│   │   └── redis.py                # Redis store and fallback
│   ├── data/
│   │   ├── ingest_properties.py    # Scraped-data normalization
│   │   └── seed_properties.py      # Curated property records
│   ├── messages/
│   │   ├── audios/                 # Download, normalize, transcribe
│   │   ├── chats/                  # Text handling and Redis history
│   │   ├── interactions/           # Button/list/flow replies
│   │   ├── downloader.py            # Meta media downloader
│   │   ├── formatter.py             # WhatsApp-safe formatting/splitting
│   │   ├── parser.py                # Webhook payload parsing
│   │   ├── router.py                # Active message handlers
│   │   ├── sender.py                # WhatsApp API delivery
│   │   ├── validator.py             # HMAC signature checks
│   │   └── webhook.py               # Event-processing pipeline
│   ├── routes/
│   │   ├── telegram.py              # Telegram owner routes
│   │   ├── webhook.py               # WhatsApp routes
│   │   └── properties.py            # Property CRUD REST API routes
│   ├── services/
│   │   ├── db.py                    # Supabase data access
│   │   ├── llm.py                   # Chat Completions integration
│   │   └── telegram.py               # Telegram Bot API client
│   └── tools/
│       ├── embeddings.py             # Cloudflare Workers AI embeddings
│       ├── finance.py                # Mortgage calculator
│       ├── qdrant.py                 # Vector collection/client helpers
│       ├── registry.py               # LLM tool registry
│       ├── schedule_meeting.py       # Viewing tools
│       ├── support.py                # Contact/escalation tool
│       ├── tavily.py                 # Web search tool
│       ├── memory/                   # Profile, summaries, notifications, history
│       ├── mpesa/                    # Daraja client, tools, schemas, callbacks
│       └── properties/               # Structured and semantic property tools
├── tests/                            # Unit, integration, and live checks
└── .github/workflows/
    ├── ci.yml                        # Python 3.12/3.13 test and secret checks
    └── keep_alive.yml                # Scheduled Supabase/Qdrant pings
```

---

## Setup

### Prerequisites

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)
- FFmpeg for voice-note normalization
- A Meta WhatsApp Cloud API application and business phone number
- A Supabase project
- A Qdrant cluster
- Cloudflare Workers AI credentials for embeddings
- At least one configured LLM provider
- Redis is recommended for shared production state, but the application has an in-process fallback
- Optional: Groq for audio transcription, Tavily for web search, Telegram Bot API for owner notifications, and Safaricom Daraja for payments

### Install

```bash
git clone <repo-url>
cd Simon

# Create and activate a virtual environment if desired
uv venv
source .venv/bin/activate

# Install locked dependencies
uv sync

# Copy the repository template and fill in credentials
cp .env.example .env
```

`src/configs/settings.py` loads `.env` with override enabled, so local values should be reviewed carefully before starting the service.

### Start the API

Use the real FastAPI entrypoint:

```bash
uv run uvicorn src.main:app --reload
```

Or use the root launcher:

```bash
uv run python main.py
```

The launcher binds to `0.0.0.0:8000`, enables reload, and disables uvicorn access logs. For production, run a process manager with reload disabled and configure the platform's port and health checks appropriately.

The `webhook` Makefile target still points at the old `src.messages.webhook:app` path, and there is no `make dev` target. Prefer the direct uvicorn command above.

---

## CLI utilities

[`src/cli.py`](src/cli.py) provides operational and interactive commands:

```bash
# Check Supabase, Qdrant, embeddings, and the active LLM provider
uv run python -m src.cli status

# Seed the built-in curated dataset and index it in Qdrant
uv run python -m src.cli seed

# Index active Supabase properties in Qdrant
uv run python -m src.cli sync

# Run semantic property search
uv run python -m src.cli search "family home near schools in Nairobi" --limit 5

# Start an interactive LLM conversation
uv run python -m src.cli chat --phone 254700000000
```

Interactive chat accepts `exit`, `quit`, and `clear`.

---

## Database and indexing workflows

### Apply the schema

The schema is in [`SQl/schema.sql`](SQl/schema.sql) and creates:

- `properties`
- `customer_profiles`
- `mpesa_transactions`
- `scheduled_viewings`
- `property_inquiries`
- `conversation_summaries`
- `conversation_messages`
- `bot_settings`

It also defines property enums and indexes, a generated `price_per_sqm`, a unique property fingerprint, updated-at triggers, conversation indexes, and the unique inbound `wamid` constraint.

Apply it with a direct PostgreSQL connection:

```bash
uv run python scripts/migrate.py
```

`scripts/migrate.py` accepts `DATABASE_URL` or `SUPABASE_DB_URL`. If neither is present, it can build a Supabase pooler URL from `SUPABASE_URL` and `SUPABASE_DB_PASSWORD`.

### Seed data

Use the small curated seed:

```bash
uv run python scripts/seed_properties.py
```

Use the complete ingestion pipeline:

```bash
uv run python scripts/seed_database.py
```

The full seed combines normalized scraped records, Kangundo Road records, and curated exclusives. Both seed paths upsert into Supabase and index available properties into Qdrant.

### Diagnose the database

```bash
uv run python scripts/check_db.py
uv run python scripts/check_db.py --json
```

The diagnostic checks environment variables, DNS/TCP reachability, expected tables and columns, row access, and sample counts. Exit codes are:

- `0`: all checks passed
- `1`: one or more checks failed
- `2`: unexpected script failure

It distinguishes common discontinued-project/DNS, missing-schema, authentication, schema-mismatch, and empty-properties failures.

### Keep-alive pings

```bash
uv run python scripts/keep_alive.py
```

The standalone script performs harmless Supabase and Qdrant requests. The GitHub Actions workflow runs a similar keep-alive job every three days and supports manual dispatch. The application lifespan also starts background pings: Render every five minutes, and Supabase/Qdrant every six hours when configured.

---

## Environment variables

Copy `.env.example` to `.env`. Requiredness depends on which integrations are enabled; the table below describes the current settings rather than implying that every optional feature is needed for the API to boot.

### Core integrations

| Variable | Required for | Description |
|---|---|---|
| `SUPABASE_URL` | Durable data and customer context | Supabase project URL |
| `SUPABASE_KEY` | Durable data and customer context | Backend Supabase API key; never expose it to clients |
| `QDRANT_URL` | Semantic property search/indexing | Qdrant cluster URL |
| `QDRANT_API_KEY` | Authenticated Qdrant clusters | Qdrant API key |
| `CLOUDFLARE_ACCOUNT_ID` | Embeddings | Cloudflare account ID |
| `CLOUDFLARE_API_TOKEN` | Embeddings | Cloudflare Workers AI token |
| `META_ACCESS_TOKEN` | WhatsApp sending | Meta Graph API access token |
| `META_PHONE_NUMBER_ID` | WhatsApp sending | Business phone-number ID |
| `META_VERIFY_TOKEN` | `GET /webhook` verification | Token configured in Meta webhook settings |
| `META_APP_SECRET` | Secure webhook POST verification | Meta app secret used for HMAC-SHA256 |

### LLM providers

Configure either a custom endpoint or one of the automatically detected providers.

| Variable | Description |
|---|---|
| `LLM_PROVIDER` | Explicit provider selection when supported by the resolver |
| `LLM_BASE_URL` | Custom OpenAI-compatible API base URL |
| `LLM_API_KEY` | Key for the custom endpoint |
| `LLM_MODEL` | Model for the custom endpoint or explicit provider override |
| `LLM_TEMPERATURE` | Sampling temperature, default `0.7`, clamped to `0.0`–`2.0` |
| `LLM_MAX_OUTPUT_TOKENS` | Maximum model output tokens, default `4096` |
| `LLM_MAX_TOOL_ITERATIONS` | Maximum tool loop iterations, default `10` |
| `NVIDIA_API_KEY` | NVIDIA provider key; first automatic provider |
| `OPENROUTER_API_KEY` | OpenRouter provider key; second automatic provider |
| `GROQ_API_KEY` | Groq chat and transcription key |
| `GROQ_STT_MODEL` | Groq Whisper model, default `whisper-large-v3` |
| `GEMINI_API_KEY` | Loaded compatibility setting; Gemini is not currently selected by the active chat resolver |

### Conversation and formatting

| Variable | Default | Description |
|---|---:|---|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string |
| `MAX_HISTORY` | `10` | Number of recent Redis history entries per customer |
| `CONVERSATION_TTL_SECONDS` | `604800` | Redis history TTL; seven days by default |
| `WHATSAPP_MAX_MESSAGE_LENGTH` | `4096` | Maximum outgoing WhatsApp message length |
| `WHATSAPP_TABLE_MODE` | `text` | Table formatting setting; current output is readable plain text |
| `WHATSAPP_FORMAT_DEBUG` | `false` | Formatter debug logging |
| `NORMALISER_DISABLED` | unset | Set to `true` only when intentionally disabling audio normalization |
| `LOCAL_DEV` | unset | Allows missing Meta app-secret verification only for explicit local development values `1`, `true`, or `yes` |

### Optional tools and owner integrations

| Variable | Description |
|---|---|
| `TAVILY_API_KEY` | Enables `web_search` |
| `TELEGRAM_BOT_TOKEN` | Enables Telegram Bot API operations |
| `SIMON_CHAT_ID` | Fallback owner Telegram chat ID; `/start` can persist it dynamically |
| `RENDER_BASE_URL` | Public Render URL for keep-alive and Telegram webhook setup |
| `WEBHOOK_CALLBACK_URL` | Deployment callback URL used by deployment integrations |
| `SAMANTHA_API_KEY` | Compatibility/application setting |
| `SAMANTHA_API_KEY_ID` | Compatibility/application setting |
| `SAMANTHA_CLUSTER_ENDPOINT` | Compatibility/application setting |
| `SAMANTHA_CLUSTER_ID` | Compatibility/application setting |
| `PROPERTY_ADMIN_USER` | Username for property write API endpoints (default `admin`) |
| `PROPERTY_ADMIN_PASSWORD` | Password for property write API endpoints (default `changeme` — change in production) |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed origins for cross-origin requests from external websites (default `*` — restrict in production) |

### M-Pesa and database migration settings

| Variable | Description |
|---|---|
| `CONSUMER_KEY` | Safaricom Daraja consumer key |
| `CONSUMER_SECRET` | Safaricom Daraja consumer secret |
| `PASSKEY` | Daraja STK Push passkey |
| `SHORTCODE` | Business shortcode or till configuration |
| `CALLBACK_URL` | Daraja STK callback URL |
| `MPESA_WEBHOOK_SECRET` | Secret path segment for M-Pesa callback routes |
| `DATABASE_URL` | Direct PostgreSQL URL for `scripts/migrate.py` |
| `SUPABASE_DB_URL` | Alternate direct PostgreSQL URL for migrations |
| `SUPABASE_DB_PASSWORD` | Used with `SUPABASE_URL` to construct a Supabase pooler URL |

Do not commit `.env`, API tokens, private keys, certificates, database URLs, or callback secrets. Backend keys such as `SUPABASE_KEY`, `META_ACCESS_TOKEN`, and M-Pesa credentials must remain server-side.

---

## Testing and CI

Install development dependencies with `uv sync` and run:

```bash
# Full test suite
uv run python -m pytest tests/ -v --tb=short

# Formatter tests
uv run python -m pytest tests/test_formatter.py -v
uv run python -m pytest tests/test_formatter_splitter.py -v

# A focused test file
uv run python -m pytest tests/test_llm.py -v
```

The GitHub Actions workflow runs on pushes and pull requests to `main` against Python 3.12 and 3.13. It installs the package with `pip install -e ".[dev]"`, runs the test suite, supplies test environment values, and performs a tracked-secret scan.

The repository includes unit tests, integration-style tests, data-integrity tests, provider checks, audio/downloader hardening tests, formatter tests, M-Pesa tests, tool-registry tests, and optional live-service checks. Tests that require live Supabase, Qdrant, Cloudflare, NVIDIA, or other external services should be run only when their credentials and service availability are intentionally configured.

---

## Operational and security notes

- Keep `META_APP_SECRET` configured in every non-local environment. The local bypass is explicit and should never be enabled for a public deployment.
- Treat `SUPABASE_KEY` as a backend credential. Do not put it in browser or mobile client code.
- The M-Pesa callback secret is not a cryptographic signature. Add network-level restrictions before handling real money.
- WhatsApp webhook deduplication is keyed by WAMID in Redis and inbound message persistence is protected by a unique database constraint. Use shared Redis in multi-worker deployments; the local fallback is process-local.
- The Redis window expires after seven days, but durable Supabase conversation messages currently do not have an automatic retention task.
- The default Daraja base URL is the sandbox. Verify all payment configuration before enabling a production account.
- The application acknowledges validly signed WhatsApp events even when downstream work fails. Monitor logs and durable message state for handler failures rather than relying on Meta retries.
- Shared HTTP clients are closed by the FastAPI lifespan. Avoid creating unbounded clients inside handlers.
- Audio files are temporary and removed after processing; FFmpeg and Groq credentials should be installed only in trusted runtime environments.
- Rotate any credential that has ever been committed to repository history or tracked deployment configuration, even if the file is later deleted.

---

## Makefile status

The Makefile contains useful convenience commands, but several entries are stale and should not be treated as the canonical interface:

- `make test` runs pytest.
- `make keep-alive` runs `scripts/keep_alive.py`.
- `make clean` removes Python caches.
- `make dev` does not exist.
- `make webhook` points to the obsolete `src.messages.webhook:app` target instead of `src.main:app`.
- `make gemini`, `make sql`, `make mpesa`, and some diagnostic targets reference modules or paths that are not current application entrypoints.

Use the direct `uv run` commands documented above until those targets are corrected.

---

## License

Proprietary — all rights reserved.
