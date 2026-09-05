# Website Integration Reference (Technical)

> 👋 This is the **technical reference** for connecting an external website to
> **Simon agent**. For the plain-language, vibe-coder-friendly walkthrough (the
> ready-to-paste lovable.ai prompt), see
> [`EXTERNAL_WEBSITE_INTEGRATION.md`](./EXTERNAL_WEBSITE_INTEGRATION.md).

This reference explains how an external website connects to **Simon agent** so
that:

1. Properties added on the site are saved into Simon's database.
2. Customers can **search** the same shared pool of listings.
3. Visitors can talk to **Simon agent** embedded as a **sidebar / chat bubble**.

---

## What Simon exposes today

Simon is a FastAPI application. The base URL is the live deployment:

```
https://samantha-nrev.onrender.com
```

> ℹ️ **Name note:** the deployment address and the `SAMANTHA_WEB_API_KEY` env var
> still carry the assistant's old working name. They are the current, correct
> values — keep them exactly as shown.

| Purpose | Method | Path | Auth |
|---|---|---|---|
| Submit / update a property → DB | `POST` | `/api/properties/` | HTTP Basic (`PROPERTY_ADMIN_USER` / `PROPERTY_ADMIN_PASSWORD`) |
| Search available properties (shared pool) | `GET` | `/api/properties/` | none (public) |
| Get one property's full detail | `GET` | `/api/properties/{id}` | none (public) |
| Count matching properties | `GET` | `/api/properties/total` | none (public) |
| Chat with Simon agent (web widget) | `POST` | `/api/chat/` | `X-API-Key` header (if `SAMANTHA_WEB_API_KEY` is set) |
| Chat widget JS asset | `GET` | `/static/chat-widget.js` | none |

CORS is enabled on the API. By default it allows **all origins**; restrict it in
production by setting `CORS_ALLOWED_ORIGINS` to the site's domain (currently set
to `https://www.realtorroundtables.co.ke/`).

---

## Credentials the site owner receives

These values live in Simon's environment (`.env`) and are **never** exposed to
browsers:

- `PROPERTY_ADMIN_USER` / `PROPERTY_ADMIN_PASSWORD` — HTTP Basic credentials for
  the property-write endpoints.
- `SAMANTHA_WEB_API_KEY` — a shared secret for the chat endpoint (optional but
  recommended; if left unset the chat endpoint is open).

> ⚠️ **Keep write credentials server-side.** Never put `PROPERTY_ADMIN_*` in
> browser JavaScript. Property *submission* should go through the website's own
> backend so the credentials stay hidden. Property *search* and the *chat widget*
> are safe to call from the browser directly.

---

## 1 — Property submission (website → database)

When a user on the site fills in a property, send it to the database by POSTing
to `/api/properties/`.

### Request

```bash
curl -X POST "https://samantha-nrev.onrender.com/api/properties/" \
  -u "your-admin-user:your-admin-password" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "4-Bedroom Townhouse in Kilimani",
    "description": "Spacious family townhouse...",
    "property_type": "townhouse",
    "listing_type": "sale",
    "price_period": "one_time",
    "price": 28000000,
    "bedrooms": 4,
    "bathrooms": 3,
    "square_meters": 320,
    "location": "Kilimani",
    "city": "Nairobi",
    "county": "Nairobi",
    "country": "Kenya",
    "amenities": ["garden", "parking", "security"],
    "furnished": false,
    "images": [
      { "url": "https://your-site.com/img/1.jpg", "is_featured": true },
      { "url": "https://your-site.com/img/2.jpg" }
    ],
    "agent": {
      "first_name": "Realtor",
      "agency_name": "Realtor Round Tables",
      "phone": "0701454854",
      "email": "info@your-domain.com"
    },
    "source": "your-domain.com"
  }'
```

### Field contract (`CreatePropertySchema`)

**Required:**
- `title` (string, ≥3 chars)
- `description` (string, ≥10 chars)
- `property_type` — one of: `house`, `apartment`, `land`, `commercial`,
  `townhouse`, `villa`, `cottage`, `penthouse`, `studio`
- `listing_type` — `sale` or `rent`
- `price` (number, > 0)
- `location` (string, ≥2 chars)

**Optional — core fields:**
`property_subtype`, `price_period` (`one_time` / `per_month` / `per_night`),
`currency` (default `KES`), `status` (default `available`), `address`, `town`,
`city` (default `Nairobi`), `county`, `country` (default `Kenya`), `latitude`,
`longitude`, `video_url`, `source`.

**Optional — residential attributes:**
`bedrooms`, `bathrooms`, `square_meters`, `lot_size_sqm`, `plot_dimensions`,
`land_size_raw`, `year_built`, `floor_number`, `total_floors`.

**Optional — features:**
- `amenities` — list of feature tags, e.g. `["swimming_pool", "garden",
  "parking", "security"]`. The old separate booleans (`has_garden`,
  `has_swimming_pool`, `pet_friendly`, `gated_community`, `parking_spots`) are
  **gone** — fold them into `amenities` instead.
- `furnished` (boolean, default `false`).

**Optional — media:**
- `images` — list of objects `{ "url": string, "sort_order"?: int,
  "is_featured"?: bool }`. Plain URL strings are **not** accepted. The first
  image becomes featured if none is flagged.

**Optional — agent:**
- `agent` — an object with `first_name` (required), `last_name`, `email`,
  `phone`, `agency_name`, `bio`, `is_verified`, `avatar_url`. The agent is
  find-or-created by phone/email and linked via `agent_id`.
- `agent_id` — an existing agent UUID, to link instead of the `agent` object.

### What happens after you POST

- Simon upserts the row into **Supabase** (`properties` table). Re-submitting
  the same `title + location + price + listing_type + property_type +
  price_period` updates the existing row in place (no duplicates).
- The `agent` (if given) is find-or-created in the `agents` table and linked via
  `agent_id`; the `images` gallery is stored in `property_images` (featured
  first).
- The property is **immediately indexed into Qdrant**, so it appears in both
  `semantic_search_properties` (natural-language) and `search_properties`
  (structured filters) within seconds.
- Returns `{"id": "<uuid>", "status": "created", "title": "..."}` with HTTP 201.

### From your website

In your backend (Node/Express, Django, etc.) proxy the request so the Basic
credentials stay secret:

```js
// Example: your backend endpoint that forwards to Simon
app.post('/my-api/submit-property', async (req, res) => {
  const resp = await fetch('https://samantha-nrev.onrender.com/api/properties/', {
    method: 'POST',
    headers: {
      'Authorization': 'Basic ' + Buffer.from('YOUR_USER:YOUR_PASS').toString('base64'),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(req.body),
  });
  const data = await resp.json();
  res.status(resp.status).json(data);
});
```

Then your frontend `<form>` POSTs to `/my-api/submit-property`.

---

## 2 — Letting customers search the shared database pool

Visitors can search **all** listings (including newly submitted ones) using the
**public** search endpoint — no credentials needed, and CORS is open.

### Search request (browser JavaScript)

```js
// Structured search
const params = new URLSearchParams({
  location: 'Kilimani',
  listing_type: 'sale',
  min_price: '10000000',
  max_price: '50000000',
  bedrooms: '3',
  amenities: 'pool,garden',   // property must have ALL of these
  sort_by: 'price',
  sort_order: 'asc',
  limit: '20',
  offset: '0',
});

const res = await fetch(
  'https://samantha-nrev.onrender.com/api/properties/?' + params
);
const { total, results } = await res.json();
// results[i] = { id, title, price, bedrooms, bathrooms, location, city,
//                images, agent, ... }
```

### Full list of search filters

`location`, `town`, `city`, `country`, `property_type`, `listing_type`,
`price_period`, `property_subtype`, `min_price`, `max_price`, `bedrooms`,
`min_bedrooms`, `min_sqm`, `max_sqm`, `min_lot_size_sqm`, `max_lot_size_sqm`,
`amenities` (all must be present), `furnished`, `sort_by`
(`price`/`bedrooms`/`square_meters`/`created_at`), `sort_order` (`asc`/`desc`),
`limit` (1–200), `offset`.

> **Note:** feature filters use `amenities` tags (e.g. `pool`, `garden`,
> `parking`) — the old `pet_friendly` / `gated_community` query booleans are no
> longer accepted.

### Get full details for one listing

```js
const res = await fetch(
  'https://samantha-nrev.onrender.com/api/properties/' + propertyId
);
const detail = await res.json(); // full description, images, agent contact, etc.
```

---

## 3 — Embedding Simon agent as a chat bubble / sidebar

Simon agent is a full AI real-estate agent: it can search properties, show
details, compare listings, schedule viewings, remember preferences, and hand off
to the owner via Telegram. Embed it with **one script tag**.

### Option A — Drop-in widget (recommended)

```html
<!-- 1. Configure (place BEFORE the script tag) -->
<script>
  window.SimonChatConfig = {
    apiBase: "https://samantha-nrev.onrender.com",
    apiKey: "YOUR-SAMANTHA-WEB-API-KEY",   // provided by Simon (omit if unset)
    title: "Simon agent",                     // optional
    brandColor: "#0d6efd",                 // optional — matches your brand
    position: "right",                     // "left" or "right"
    welcomeMessage: "Hi! I'm Simon agent — your Kenya real-estate assistant 👋"
  };
</script>

<!-- 2. Load the widget -->
<script src="https://samantha-nrev.onrender.com/static/chat-widget.js"></script>
```

The widget:

- Generates and persists a **session id** in the visitor's `localStorage` (so the
  conversation continues across page reloads).
- Sends each message to `POST /api/chat/` with `{ session_id, message }`.
- Renders Simon agent's reply (which may include tool-driven searches of the
  shared property pool).
- Is dependency-free and self-contained.

### Option B — Build your own UI

```js
const res = await fetch('https://samantha-nrev.onrender.com/api/chat/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'YOUR-SAMANTHA-WEB-API-KEY',  // if SAMANTHA_WEB_API_KEY is set
  },
  body: JSON.stringify({
    session_id: 'web-visitor-123',   // any unique identifier you manage
    message: '3-bedroom apartment for rent in Westlands under 150k',
  }),
});
const data = await res.json();
// data.reply  -> Simon agent's text response
// data.session_id -> the session id to reuse on the next call
```

### What visitors can do with Simon agent

Because Simon agent has the full tool registry, a web visitor can:

- Search the shared property pool (`search_properties` / `semantic_search_properties`)
- See full property details, photos, agent contacts
- Compare properties side by side
- Book a viewing appointment
- Ask market / mortgage questions
- Be handed off to the owner via Telegram notifications

Sessions are persisted to Supabase (`conversation_messages`) and Redis (history
cache), so web chat histories are visible alongside WhatsApp chats.

---

## 4 — Database tables (what the database accepts)

The database is PostgreSQL on Supabase. These are the **ten tables** that exist:

| Table | Purpose | Written by website? |
|---|---|---|
| `properties` | Property listings — price, type, location, features, status. | ✅ On submit |
| `agents` | Normalized listing-agent / agency profiles. | ✅ On submit (find-or-create) |
| `property_images` | Ordered image gallery per property (featured first). | ✅ On submit |
| `property_inquiries` | "Contact us" leads / inquiries. | ✅ When a visitor inquires |
| `customer_profiles` | Visitor/customer preferences + free-form metadata (JSONB). | 🔄 Via chat memory |
| `conversation_messages` | Full chat history (web + WhatsApp); idempotent via `wamid`. | 🔄 Chat widget |
| `conversation_summaries` | Rolling conversation summaries per customer. | 🔄 Via chat |
| `scheduled_viewings` | Booked viewing appointments (status: confirmed/rescheduled/cancelled/completed). | 🔄 Via chat (bookings) |
| `mpesa_transactions` | M-Pesa payment records. | — |
| `bot_settings` | System settings, e.g. the owner's Telegram chat ID. | — |

**Key constraints worth knowing:**

- `properties` has a unique "fingerprint" on
  `(title, location, price, listing_type, property_type, price_period)`, which is
  what makes re-submissions update-in-place instead of duplicating.
- `property_images` is unique per `(property_id, sort_order)`.
- `agents` has unique (partial) indexes on `phone` and `email` (where not null),
  which is what the find-or-create logic relies on.
- `conversation_messages.id` is `BIGSERIAL`; `content` is JSONB; `wamid` is a
  unique inbound-message id used for webhook deduplication.
- Deleting a `properties` row cascades to its `property_images`, and sets the
  linked `agent_id` on inquiries to NULL; `property_inquiries.agent_id` is also
  set to NULL if the agent is deleted.

---

## Quick checklist for the website owner

- [ ] Receive `PROPERTY_ADMIN_USER` / `PROPERTY_ADMIN_PASSWORD` from Simon.
- [ ] Wire the property-form backend to `POST /api/properties/`.
- [ ] Call `GET /api/properties/` from the frontend to show search results.
- [ ] Receive `SAMANTHA_WEB_API_KEY` from Simon (optional but recommended).
- [ ] Add the chat-widget `<script>` snippet to the site.
- [ ] (Production) Confirm `CORS_ALLOWED_ORIGINS` is set to the site's domain.