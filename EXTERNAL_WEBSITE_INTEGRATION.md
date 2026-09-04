# External Website Integration — What the Partner Needs to Do

This document is the **complete, relayable instruction set** for an external
website owner (e.g. Damantha) to connect their website to **Simon / Samantha**
and embed the Samantha chat assistant. Your (Simon's) backend is already set
up — everything below is what the partner does on **their** end.

---

## 0. Your base API URL

All endpoints are served from your Simon deployment:

```
https://samantha-nrev.onrender.com
```

---

## 1. Credentials the partner needs from you (Simon)

Share these **privately** (never commit them to her frontend code):

| What she needs | Your env var | How she uses it |
|---|---|---|
| Property-submit username / password | `PROPERTY_ADMIN_USER` + `PROPERTY_ADMIN_PASSWORD` | HTTP Basic auth for `POST /api/properties/` |
| Chat-widget key (recommended) | `SAMANTHA_WEB_API_KEY` | Sent as the `X-API-Key` header to `POST /api/chat/` |

> ⚠️ Her property-submission calls **must go through her own backend** so the
> Basic credentials never appear in browser JavaScript. Her chat widget and
> search calls can be browser-side (CORS is open by default; in production you
> restrict it via `CORS_ALLOWED_ORIGINS`).

---

## 2. Push properties from her site to your database

**Endpoint:**
```
POST https://samantha-nrev.onrender.com/api/properties/
```

**Her backend** sends each property as JSON with HTTP Basic auth:
```
Authorization: Basic base64(YOUR_USER:YOUR_PASS)
Content-Type: application/json
```

### Field mapping (her form → your schema `CreatePropertySchema`)

**Required** (she must collect these):
- `title` (string) — listing title
- `description` (string, ≥10 chars)
- `property_type` — **exactly one of:** `house`, `apartment`, `land`, `commercial`, `townhouse`, `villa`, `cottage`, `penthouse`, `studio`
- `listing_type` — `sale` or `rent`
- `price` (number, > 0)
- `location` (string) — neighborhood/area, e.g. `"Kilimani"`

**Optional** (map as she collects them):
- `city` (default `Nairobi`), `county`
- `bedrooms`, `bathrooms`, `square_meters`, `lot_size_sqm`, `year_built`, `floor_number`, `total_floors`
- `currency` (default `KES`)
- `amenities` (list, e.g. `["garden","parking","security"]`)
- `furnished` (bool), `parking_spots` (int)
- `has_garden`, `has_swimming_pool`, `pet_friendly`, `gated_community` (bools)
- `images` (list of image URLs), `video_url`, `virtual_tour_url`
- `agent_name`, `agent_phone`, `agent_email`
- `source` — she can set `"source": "damantha.com"` to track where the listing came from

### Example request (her backend)

```bash
curl -X POST "https://samantha-nrev.onrender.com/api/properties/" \
  -u "PROPERTY_ADMIN_USER:PROPERTY_ADMIN_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "4-Bedroom Townhouse in Kilimani",
    "description": "Spacious family townhouse with garden and parking in a secure complex.",
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
    "images": ["https://her-site.com/img/1.jpg", "https://her-site.com/img/2.jpg"],
    "agent_name": "Damantha Real Estate",
    "agent_phone": "0701454854",
    "agent_email": "info@damantha.com",
    "source": "damantha.com"
  }'
```

### What happens automatically (her responsibility: nothing)
- The listing is **upserted into Supabase** (your PostgreSQL database). Resubmitting
  the same `title + location + price + listing_type + property_type` updates the
  existing row — no duplicates.
- The property is **instantly indexed into Qdrant**, so it appears in both
  structured and natural-language (semantic) searches by every customer immediately.

### Response
```
201 Created
{ "id": "<uuid>", "status": "created", "title": "4-Bedroom Townhouse in Kilimani" }
```

### From her website (backend proxy pattern)

```js
// Example: her backend endpoint that forwards to your Simon API
app.post('/my-api/submit-property', async (req, res) => {
  const resp = await fetch('https://samantha-nrev.onrender.com/api/properties/', {
    method: 'POST',
    headers: {
      'Authorization': 'Basic ' + Buffer.from('PROPERTY_ADMIN_USER:PROPERTY_ADMIN_PASSWORD').toString('base64'),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(req.body),
  });
  const data = await resp.json();
  res.status(resp.status).json(data);
});
```

Then her frontend `<form>` POSTs to `/my-api/submit-property` (her own backend),
which keeps the credentials secret.

---

## 3. Let her customers search your shared database pool

**Endpoint:**
```
GET https://samantha-nrev.onrender.com/api/properties/
```
**No auth needed** — her frontend calls it directly (CORS is open).

### Full list of query parameters she can wire to her search UI

| Parameter | Type | Description |
|---|---|---|
| `location` | text | Fuzzy match on neighborhood/area |
| `city` | text | City name (e.g. `Nairobi`, `Mombasa`) |
| `property_type` | enum | `house`, `apartment`, `land`, `commercial`, `townhouse`, `villa`, `cottage`, `penthouse`, `studio` |
| `listing_type` | enum | `sale` or `rent` |
| `min_price` | number | Minimum price in KES |
| `max_price` | number | Maximum price in KES |
| `bedrooms` | int | Exact bedroom count |
| `min_bedrooms` | int | Minimum bedrooms |
| `min_sqm` | number | Minimum square meters |
| `max_sqm` | number | Maximum square meters |
| `amenities` | list | Property must have all of these |
| `furnished` | bool | Filter by furnished status |
| `pet_friendly` | bool | Filter by pet-friendly status |
| `gated_community` | bool | Filter by gated community status |
| `sort_by` | enum | `price`, `bedrooms`, `square_meters`, `created_at` |
| `sort_order` | enum | `asc` or `desc` |
| `limit` | int (1–200) | Results per page |
| `offset` | int | Pagination offset |

### Example (browser JavaScript)

```js
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
// results[i] = { id, title, price, currency, bedrooms, bathrooms,
//                  property_type, listing_type, location, city, amenities, image }
```

### Single property detail (browser)

```js
const res = await fetch(
  'https://samantha-nrev.onrender.com/api/properties/' + propertyId
);
const detail = await res.json(); // full description, images, agent contact, etc.
```

### Quick count for stats

```
GET https://samantha-nrev.onrender.com/api/properties/total?location=Kilimani&listing_type=sale
→ { "count": N }
```

---

## 4. Embed Samantha as a chat bubble / sidebar

Samantha is a full AI real-estate agent. A visitor on her site can ask her to
search properties, compare listings, view photos, schedule viewings, save
preferences, and even be handed off to you (Simon). She reuses your existing
LLM + tool pipeline — just delivered as JSON instead of via WhatsApp.

### Option A — Drop-in widget (recommended)

She adds **two script tags** to her site (in `<head>` or before `</body>`):

```html
<!-- 1. Configure (place BEFORE the widget script) -->
<script>
  window.SimonChatConfig = {
    apiBase: "https://samantha-nrev.onrender.com",   // your Simon URL
    apiKey: "SAMANTHA_WEB_API_KEY-value-here",         // from you (omit if you left the key unset)
    title: "Samantha",                                  // optional — chat header
    brandColor: "#0d6efd",                              // optional — match her brand
    position: "right",                                  // "left" or "right" (default: right)
    welcomeMessage: "Hi! I'm Samantha, your Kenya real-estate assistant 👋"
  };
</script>

<!-- 2. Load the widget (single script tag) -->
<script src="https://samantha-nrev.onrender.com/static/chat-widget.js"></script>
```

**What the widget does automatically:**
- Injects a floating chat button in the bottom corner.
- On click, opens a chat panel (sidebar-style).
- Generates and persists a **session id** in the visitor's `localStorage`
  (so the conversation continues across page reloads).
- Sends each message to `POST /api/chat/` with `{ session_id, message }`
  and the `X-API-Key` header, then renders Samantha's reply.
- Shows a "Samantha is typing…" indicator while waiting.

It's dependency-free and works on any modern browser.

### Option B — Build her own chat UI

If she wants full control of the look & feel, she calls the API directly:

```
POST https://samantha-nrev.onrender.com/api/chat/
Headers: Content-Type: application/json, X-API-Key: <the key>
Body: {
  "session_id": "web-<any-visitor-id>",   // generated/persisted by her
  "message": "3 bedroom house in Karen"
}
```

**Response:**
```json
{
  "reply": "Samantha's text response here. She can search your property pool live.",
  "session_id": "web-<id-to-reuse-on-next-call>",
  "source": "web"
}
```

She reuses the returned `session_id` on every subsequent call from the same
visitor so the conversation stays contextual.

#### Response shape explained
| Field | Meaning |
|---|---|
| `reply` | Samantha's text answer (may include property search results from your DB) |
| `session_id` | The session id to send back next time |
| `source` | Always `"web"` for the widget channel |

---

## 5. Production hardening (your job, Simon — tell her to ask for this)

- **Restrict CORS** to her domain: set `CORS_ALLOWED_ORIGINS=https://damantha.com`
  in your environment (instead of the default `*`).
- **Never expose** `PROPERTY_ADMIN_PASSWORD` or `SUPABASE_KEY` to the browser.
- When `SAMANTHA_WEB_API_KEY` is set, every chat request **must** include the
  matching `X-API-Key` header (the widget handles this automatically).

---

## 6. Checklist for the partner (Damantha)

- [ ] Receive `PROPERTY_ADMIN_USER` + `PROPERTY_ADMIN_PASSWORD` from Simon.
- [ ] Wire her property form → her backend → `POST https://samantha-nrev.onrender.com/api/properties/`.
- [ ] Wire her search UI → `GET https://samantha-nrev.onrender.com/api/properties/` (browser, no auth).
- [ ] Receive `SAMANTHA_WEB_API_KEY` from Simon.
- [ ] Add the two `<script>` tags (Option A) — or build her own UI with Option B.
- [ ] (Production) Ask Simon to set `CORS_ALLOWED_ORIGINS` to her domain.

---

## 7. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `401 Unauthorized` on `POST /api/properties/` | Wrong/missing Basic auth credentials. Confirm user & password with Simon. |
| Property not appearing in search | Wait a moment for Qdrant indexing, or confirm the `POST` returned `201` with an `id`. |
| `401` on `POST /api/chat/` | Missing or wrong `X-API-Key`. If the widget is used, ensure `apiKey` is set in `SimonChatConfig`. |
| Widget not showing on the page | Ensure `apiBase` is set in `window.SimonChatConfig` and the script tag loads after it. Check browser console for errors. |
| Chat returns `503` | Simon's LLM backend is temporarily unavailable; retry in a minute. |

---

For Simon's internal technical reference see [`INTEGRATION.md`](./INTEGRATION.md).
