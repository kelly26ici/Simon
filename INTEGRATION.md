# Website Integration Guide (Simon's Internal Reference)

> 👋 This is Simon's internal technical reference. For the step-by-step guide that
> an external website owner follows (written for vibe coders who use lovable.ai),
> see [`EXTERNAL_WEBSITE_INTEGRATION.md`](./EXTERNAL_WEBSITE_INTEGRATION.md).

This guide explains what an external website owner (e.g. **Damantha**) needs to do
to connect their website to **Simon agent** so that:

1. Properties added on their site are saved into **Simon's** database.
2. Their customers can **search** the same shared pool of Simon's databases.
3. Visitors on their site can talk to **Simon agent** embedded as a **sidebar / chat bubble**.

---

## What Simon exposes today

Simon is a FastAPI application. The base URL is your deployment, e.g.
`https://samantha-nrev.onrender.com`. All endpoints below are served from that origin.

| Purpose | Method | Path | Auth |
|---|---|---|---|
| Submit / update a property → Simon's DB | `POST` | `/api/properties/` | HTTP Basic (`PROPERTY_ADMIN_USER` / `PROPERTY_ADMIN_PASSWORD`) |
| Search available properties (shared pool) | `GET` | `/api/properties/` | none (public) |
| Get one property's full detail | `GET` | `/api/properties/{id}` | none (public) |
| Count matching properties | `GET` | `/api/properties/total` | none (public) |
| Chat with Simon agent (web widget) | `POST` | `/api/chat/` | `X-API-Key` header (if `SAMANTHA_WEB_API_KEY` is set) |
| Chat widget JS asset | `GET` | `/static/chat-widget.js` | none |

CORS is already enabled on the API. By default it allows **all origins**; you can
restrict it in production by setting `CORS_ALLOWED_ORIGINS` to your domain, e.g.
`CORS_ALLOWED_ORIGINS=https://damantha.com`.

---

## Step 0 — Credentials you receive from Simon

Simon must give you these values (they live in Simon's `.env` and are **never**
exposed to browsers):

- `PROPERTY_ADMIN_USER` and `PROPERTY_ADMIN_PASSWORD` — HTTP Basic credentials
  for the property-write endpoints.
- `SAMANTHA_WEB_API_KEY` — a shared secret for the chat endpoint (optional but
  recommended for production; if Simon leaves it unset the chat endpoint is open).

> ⚠️ **Keep write credentials server-side.** Never put `PROPERTY_ADMIN_*` in
> browser JavaScript. Property *submission* should go through your own backend
> so the credentials stay hidden. Property *search* and the *chat widget* are
> safe to call from the browser directly.

---

## 1 — Property submission (website → Simon's database)

When a user on Damantha's site fills in a property, send it to Simon's database
by POSTing to `/api/properties/`.

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
    "price": 28000000,
    "bedrooms": 4,
    "bathrooms": 3,
    "square_meters": 320,
    "location": "Kilimani",
    "city": "Nairobi",
    "county": "Nairobi",
    "amenities": ["garden", "parking", "security"],
    "furnished": false,
    "parking_spots": 2,
    "has_garden": true,
    "images": ["https://your-site.com/img/1.jpg"],
    "agent_name": "Damantha Real Estate",
    "agent_phone": "0701454854",
    "agent_email": "info@damantha.com",
    "source": "damantha.com"
  }'
```

### Field contract (`CreatePropertySchema`)

**Required:**
- `title` (string, ≥3 chars)
- `description` (string, ≥10 chars)
- `property_type` — one of: `house`, `apartment`, `land`, `commercial`, `townhouse`, `villa`, `cottage`, `penthouse`, `studio`
- `listing_type` — `sale` or `rent`
- `price` (number, > 0)
- `location` (string, ≥2 chars)

**Optional:**
`city` (default `Nairobi`), `county`, `bedrooms`, `bathrooms`, `square_meters`,
`lot_size_sqm`, `year_built`, `floor_number`, `total_floors`, `currency`
(default `KES`), `amenities` (list), `furnished`, `parking_spots`, `has_garden`,
`has_swimming_pool`, `pet_friendly`, `gated_community`, `images` (list of URLs),
`video_url`, `virtual_tour_url`, `agent_name`, `agent_phone`, `agent_email`,
`source`.

### What happens after you POST

- Simon upserts the row into **Supabase** (`properties` table). Re-submitting
  the same `title + location + price + listing_type + property_type` updates the
  existing row in place (no duplicates).
- The property is **immediately indexed into Qdrant**, so it appears in both
  `semantic_search_properties` (natural-language) and `search_properties`
  (structured filters) within seconds.
- Returns `{"id": "<uuid>", "status": "created", "title": "..."}` with HTTP 201.

### From your website

In your backend (Node/Express, Django, etc.) proxy the request so your Basic
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

## 2 — Letting their customers search your shared database pool

Your site's visitors can search **all** of Simon's listings (including the
properties you just submitted) using the **public** search endpoint — no
credentials needed, and CORS is open.

### Search request (browser JavaScript)

```js
// Structured search
const params = new URLSearchParams({
  location: 'Kilimani',
  listing_type: 'sale',
  min_price: '10000000',
  max_price: '50000000',
  bedrooms: '3',
  sort_by: 'price',
  sort_order: 'asc',
  limit: '20',
  offset: '0',
});

const res = await fetch(
  'https://samantha-nrev.onrender.com/api/properties/?' + params
);
const { total, results } = await res.json();
// results[i] = { id, title, price, bedrooms, bathrooms, location, city, ... }
```

### Full list of search filters

`location`, `city`, `property_type`, `listing_type`, `min_price`, `max_price`,
`bedrooms`, `min_bedrooms`, `min_sqm`, `max_sqm`, `pet_friendly`,
`gated_community`, `sort_by` (`price`/`bedrooms`/`square_meters`/`created_at`),
`sort_order` (`asc`/`desc`), `limit` (1–200), `offset`.

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
details, compare listings, schedule viewings, remember your preferences, and
even contact Simon (the owner) when you're ready. You can embed it as a
chat widget with **one script tag**.

### Option A — Drop-in widget (recommended)

Paste this on any page where you want the chat bubble to appear:

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

That's it. A floating chat button appears in the corner; visitors click it to
open the chat panel. The widget:

- Generates and persists a **session id** in the visitor's `localStorage` (so the
  conversation continues across page reloads).
- Sends each message to `POST /api/chat/` with `{ session_id, message }`.
- Renders Simon agent's reply (which may include tool-driven searches of your
  shared property pool).
- Is dependency-free and self-contained.

### Option B — Build your own UI

If you want full control of the look & feel, call the chat API directly:

```js
const res = await fetch('https://samantha-nrev.onrender.com/api/chat/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'YOUR-SAMANTHA-WEB-API-KEY',  // if Simon set SAMANTHA_WEB_API_KEY
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

- Search your shared property pool (`search_properties` / `semantic_search_properties`)
- See full property details, photos, agent contacts
- Compare properties side by side
- Book a viewing appointment
- Ask market / mortgage questions
- Be handed off to Simon (owner) via Telegram notifications

Sessions are persisted to Supabase (`conversation_messages`) and Redis
(history cache), so Simon can see web chat histories alongside WhatsApp
chats.

---

## Quick checklist for Damantha

- [ ] Receive `PROPERTY_ADMIN_USER` / `PROPERTY_ADMIN_PASSWORD` from Simon.
- [ ] Wire your property-form backend to `POST /api/properties/`.
- [ ] Call `GET /api/properties/` from your frontend to show search results.
- [ ] Receive `SAMANTHA_WEB_API_KEY` from Simon (optional but recommended).
- [ ] Add the chat-widget `<script>` snippet to your site.
- [ ] (Production) Ask Simon to set `CORS_ALLOWED_ORIGINS` to your domain.
