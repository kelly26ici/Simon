# Connect Your Website to Simon's Property Database & Simon Agent

Hi! This guide is for **you** — the owner of an external website who wants to:

1. Push property listings from your site into my (Simon's) database.
2. Let your visitors search the shared pool of my listings.
3. Embed **Simon agent** as a chat bubble on your site.

I'm the **developer** who built Simon agent. Below is a three-part plan: what **you** do, what **I** do, and what's still **remaining**.

> **Note for vibe coders:** If you build websites with lovable.ai, just copy the instructions in the blue quotes below and paste them straight into a lovable.ai chat. lovable.ai can build everything for you — no manual coding needed.

---

## 1. What You Should Do

### 1a. Credentials I'll give you

Before you can connect, I'll share these values with you privately (never post them publicly):

| What you need it for | Value I'll give you | Placeholder in this doc | Where you use it |
|---|---|---|---|
| Submit properties to my database | `PROPERTY_ADMIN_USER` / `PROPERTY_ADMIN_PASSWORD` | `[PROPERTY_ADMIN_USER]` / `[PROPERTY_ADMIN_PASSWORD]` | HTTP Basic auth header in your backend |
| Let visitors chat with Simon agent | `SAMANTHA_WEB_API_KEY` | `[SAMANTHA_WEB_API_KEY]` | `X-API-Key` header in chat requests |

**My API base URL** (confirming it's live):

```
https://samantha-nrev.onrender.com
```

> ⚠️ Your admin credentials must **never** appear in browser JavaScript. Property submission must go through your own backend (a server-side route). Search and the chat widget are safe to call directly from the browser.

---

### 1b. Tell lovable.ai: build a backend endpoint that sends properties to me

You need a **backend route on your site** (e.g. `POST /api/submit-property`) that forwards form data to my database. The admin credentials stay in your backend — not in the browser.

**Tell lovable.ai:**

> "Create a backend API route at `/api/submit-property` on my website. It should accept a POST request with JSON matching this shape, then proxy the request to `https://samantha-nrev.onrender.com/api/properties/` using HTTP Basic auth with username `[PROPERTY_ADMIN_USER]` and password `[PROPERTY_ADMIN_PASSWORD]`. Return the response back to the caller."

Your form must collect **these required fields** (the submit will fail if any are missing):

| Field | Type | Rules |
|---|---|---|
| `title` | text | at least 3 characters |
| `description` | text | at least 10 characters |
| `property_type` | dropdown | must be exactly one of: `house`, `apartment`, `land`, `commercial`, `townhouse`, `villa`, `cottage`, `penthouse`, `studio` |
| `listing_type` | dropdown | must be exactly: `sale` or `rent` |
| `price` | number | must be greater than 0 |
| `location` | text | neighborhood or area, e.g. "Kilimani" |

**Optional fields** (collect whatever is useful for your site):

| Field | Type | Notes |
|---|---|---|
| `city` | text | defaults to "Nairobi" if omitted |
| `county` | text | — |
| `bedrooms` | number | — |
| `bathrooms` | number | — |
| `square_meters` | number | — |
| `amenities` | list | e.g. `["parking", "garden", "security"]` |
| `furnished` | toggle | true/false |
| `parking_spots` | number | — |
| `has_garden` | toggle | true/false |
| `has_swimming_pool` | toggle | true/false |
| `pet_friendly` | toggle | true/false |
| `gated_community` | toggle | true/false |
| `images` | list | list of image URLs already uploaded |
| `video_url` | text | link to a video tour |
| `virtual_tour_url` | text | link to a virtual tour |
| `agent_name` | text | your listing agent name |
| `agent_phone` | text | your contact phone |
| `agent_email` | text | your contact email |
| `source` | text | e.g. "yourdomain.com" — so I know where the listing came from |

**Tell lovable.ai:**

> "Update my property submission form so that when a user fills it out and clicks submit, the form sends the data to my own `/api/submit-property` backend route (not directly to Simon's API)."

**What happens after you submit:** I'll upsert your listing into my PostgreSQL database and immediately index it into my search system. Resubmitting the same listing (matching title + location + price + type + listing_type) just updates it — no duplicates.

**Success response:**

```json
{ "id": "<uuid>", "status": "created", "title": "Your listing title" }
```

---

### 1c. Tell lovable.ai: build a search page that calls my public search

This is **browser-side only** — no credentials needed. My API allows all origins by default during testing.

**Tell lovable.ai:**

> "Create a search results page on my website. When a visitor selects filters (location, price range, bedrooms, etc.), make a GET request to `https://samantha-nrev.onrender.com/api/properties/` passing the filters as URL query parameters. Display the returned results (title, price, thumbnail image, bedrooms, location) in a grid or list."

**Available search filters** you can tell lovable.ai to wire up:

| Filter | Type | Example |
|---|---|---|
| `location` | text | `Kilimani`, `Westlands` |
| `city` | text | `Nairobi`, `Mombasa` |
| `property_type` | enum | `house`, `apartment`, `land`, `commercial`, `townhouse`, `villa`, `cottage`, `penthouse`, `studio` |
| `listing_type` | enum | `sale`, `rent` |
| `min_price` | number | `10000000` |
| `max_price` | number | `50000000` |
| `bedrooms` | integer | `3` |
| `min_bedrooms` | integer | `2` |
| `min_sqm` | number | `150` |
| `max_sqm` | number | `400` |
| `pet_friendly` | boolean | `true` / `false` |
| `gated_community` | boolean | `true` / `false` |
| `sort_by` | enum | `price`, `bedrooms`, `square_meters`, `created_at` |
| `sort_order` | enum | `asc`, `desc` |
| `limit` | integer (1–200) | `20` |
| `offset` | integer | `0`, `40` (for pagination) |

**Example result shape** (what lovable.ai receives to render):

```json
{
  "total": 24,
  "limit": 20,
  "offset": 0,
  "results": [
    {
      "id": "<uuid>",
      "title": "4-Bedroom Townhouse in Kilimani",
      "price": 28000000,
      "currency": "KES",
      "bedrooms": 4,
      "bathrooms": 3,
      "property_type": "townhouse",
      "listing_type": "sale",
      "location": "Kilimani",
      "city": "Nairobi",
      "images": ["https://..."],
      "agent_name": "Damantha Real Estate"
    }
  ]
}
```

You can also show a single property's full details (including description, all photos, agent contact info, etc.):

```
GET https://samantha-nrev.onrender.com/api/properties/{property-id}
```

---

### 1d. Tell lovable.ai: paste two script tags to embed Simon agent as a chat bubble

Add this to your site's HTML — put the first block in your `<head>` (or just before `</body>`), and the second block after it.

```html
<!-- 1. Configuration (must come BEFORE the script tag below) -->
<script>
  window.SimonChatConfig = {
    apiBase: "https://samantha-nrev.onrender.com",
    apiKey: "[SAMANTHA_WEB_API_KEY]",          // I'll give you this value
    title: "Simon agent",                       // optional — chat header text
    brandColor: "#0d6efd",                      // optional — match your brand color
    position: "right",                           // "left" or "right" (default: right)
    welcomeMessage: "Hi! I'm Simon agent — your Kenya real-estate assistant 👋"
  };
</script>

<!-- 2. Load the chat widget (single script tag) -->
<script src="https://samantha-nrev.onrender.com/static/chat-widget.js"></script>
```

> 🔑 Remember to replace `[SAMANTHA_WEB_API_KEY]` with the actual value I give you.

That's it — a floating chat button appears in the corner of your page. Visitors click it to open Simon agent and can ask questions like "3-bedroom house for rent in Westlands under 150k" or "show me properties with a garden."

**What the widget does automatically:**
- Generates and saves a session ID in the visitor's browser (`localStorage`) — conversations continue across page reloads.
- Sends each message to `POST /api/chat/` with the `X-API-Key` header.
- Shows a "Simon agent is typing…" indicator while waiting.
- Is fully self-contained — no npm packages, no dependencies.

If you'd rather build your own chat UI instead of using the widget, the chat endpoint is:

```
POST https://samantha-nrev.onrender.com/api/chat/
Headers: Content-Type: application/json, X-API-Key: [SAMANTHA_WEB_API_KEY]
Body: { "session_id": "web-visitor-123", "message": "3 bedroom house in Karen" }
```

**Response:**

```json
{
  "reply": "Simon agent's text response here.",
  "session_id": "web-visitor-123",
  "source": "web"
}
```

Reuse the returned `session_id` on every subsequent message so the conversation stays contextual.

---

## 2. What I (the developer) Should Do

These are my tasks on the Simon backend side:

1. **Set the property admin credentials.**
   I need to set `PROPERTY_ADMIN_USER` and `PROPERTY_ADMIN_PASSWORD` in my `.env` file. The code currently defaults to `admin` / `changeme` — I must replace these with strong, unique values and share them with you.
   → Current placeholder: `[PROPERTY_ADMIN_USER]`, `[PROPERTY_ADMIN_PASSWORD]`

2. **Set the Simon agent web API key.**
   I need to set `SAMANTHA_WEB_API_KEY` in my `.env`. Without it the chat endpoint is open to anyone; with it, every chat request must include the matching `X-API-Key` header.
   → Current placeholder: `[SAMANTHA_WEB_API_KEY]`

3. **Deploy and confirm the API is live.**
   My backend is already configured with `RENDER_BASE_URL=https://samantha-nrev.onrender.com` in my `.env`. I need to confirm the deployment is running and all endpoints respond.

4. **Serve the chat widget.**
   Done — the widget is already mounted as a static file at `/static/chat-widget.js` via FastAPI in `src/main.py`. No action needed once deployed.

5. **(Production, after you give me your domain)** Restrict CORS.
   I'll set `CORS_ALLOWED_ORIGINS=https://your-domain.com` in my `.env` so only your site can call my APIs from a browser. Right now it defaults to `*` (all origins — fine for testing, not for production).

6. **Monitor and support.**
   I'll keep an eye on Simon agent's logs for any integration errors and help you debug if something doesn't work.

---

## 3. What's Remaining

| # | Item | Who owns it | Status |
|---|---|---|---|
| 1 | `PROPERTY_ADMIN_USER` — not set in `.env` (code defaults to `admin`) | I | ⚠️ Must set to a strong value |
| 2 | `PROPERTY_ADMIN_PASSWORD` — not set in `.env` (code defaults to `changeme`) | I | ⚠️ Must set to a strong value |
| 3 | `SAMANTHA_WEB_API_KEY` — not set in `.env` (code defaults to empty = open access) | I | ⚠️ Must set for production |
| 4 | `CORS_ALLOWED_ORIGINS` — not set (defaults to `*` = all origins) | I | ⚠️ Must restrict to your domain |
| 5 | Your website's domain name | You | ❓ I need this from you to configure CORS |
| 6 | Your property form fields → mapping to my API payload | You | ❓ Confirm which fields your form collects |

---

## Checklist for You

- [ ] Receive `[PROPERTY_ADMIN_USER]` / `[PROPERTY_ADMIN_PASSWORD]` from I.
- [ ] Tell lovable.ai to build your `/api/submit-property` backend route → `POST https://samantha-nrev.onrender.com/api/properties/` with Basic auth using the credentials from I.
- [ ] Tell lovable.ai to build your search page → `GET https://samantha-nrev.onrender.com/api/properties/?<filters>`.
- [ ] Receive `[SAMANTHA_WEB_API_KEY]` from I.
- [ ] Paste the two `<script>` tags on your site to embed Simon agent.
- [ ] Give I your domain name (e.g. `https://your-site.com`) so I can configure CORS for production.
- [ ] (Production) Confirm with I that `CORS_ALLOWED_ORIGINS` is set to your domain.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| `401 Unauthorized` when submitting a property | The admin credentials are wrong — ask I to confirm `[PROPERTY_ADMIN_USER]` / `[PROPERTY_ADMIN_PASSWORD]`. |
| Property not appearing in search | Wait a few seconds for indexing, or confirm your `POST` returned `{"id": ...}` with HTTP 201. |
| `401` on the chat widget | The `apiKey` in `SimonChatConfig` doesn't match — ask I to confirm `[SAMANTHA_WEB_API_KEY]`. |
| Chat bubble doesn't appear | Make sure `apiBase` is set in `window.SimonChatConfig` and the `<script src=...>` tag loads **after** it. Check your browser's developer console for errors. |
| Chat returns `503` | Simon agent's AI backend is temporarily unavailable — try again in a minute. |

---

> 📄 For Simon's internal technical reference (endpoint specs, schemas, deployment notes), see [`INTEGRATION.md`](./INTEGRATION.md).
