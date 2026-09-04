# Connect Your Website to Simon's Property Database & Simon Agent

Hi! This guide is for **you** — the owner of an external website who wants to:

1. Push property listings from your site into my (Simon's) database.
2. Let your visitors search the shared pool of my listings.
3. Embed **Simon agent** as a chat bubble on your site.

I'm the **developer** who built Simon agent. Below is a three-part plan: what **you** do, what **I** do, and what's still **remaining**.

> **Note for vibe coders:** If you build websites with lovable.ai, go straight to section 1b. I've written **one single prompt** you can copy-paste into lovable.ai — it builds everything at once. No manual coding needed.

---

## 1. What You Should Do

### 1a. Credentials

These are the values I've generated and added to my Render environment. Keep them **private** — never commit them to your frontend code or share them publicly.

| What you need it for | Env var name | Value | Where you use it |
|---|---|---|---|
| Submit properties to my database | `PROPERTY_ADMIN_USER` | `admin_Xkga15AyFnw` | HTTP Basic auth (username) in your backend |
| Submit properties to my database | `PROPERTY_ADMIN_PASSWORD` | `GILFJf_9DKFVzh0M8QcaOSuiUQG5E8Od` | HTTP Basic auth (password) in your backend |
| Let visitors chat with Simon agent | `SAMANTHA_WEB_API_KEY` | `sk-web-RPW0zl8nX7mCVyArcgE3fy6OZl5k1Aa7dHjxB1Sar-k` | `X-API-Key` header in chat requests |

**My API base URL** (live, confirmed):

```
https://samantha-nrev.onrender.com
```

> ⚠️ Your admin credentials must **never** appear in browser JavaScript. Property submission must go through your own backend (a server-side route). Search and the chat widget are safe to call directly from the browser.

---

### 1b. One lovable.ai prompt — copy & paste this whole block

Select everything below (from "I need you to implement" to the end of the script tag), paste it into a new lovable.ai chat, and let it build all three features at once:

> I need you to implement three features on my website that connect to Simon agent's API at `https://samantha-nrev.onrender.com`. Please build all three:
>
> **Feature 1 — Backend property submission endpoint**
>
> Create a backend API route at `POST /api/submit-property` on my website. It accepts a POST request with JSON and proxies the request to `https://samantha-nrev.onrender.com/api/properties/` using HTTP Basic auth with username `admin_Xkga15AyFnw` and password `GILFJf_9DKFVzh0M8QcaOSuiUQG5E8Od`. Return the response back to the caller.
>
> The **required** fields my form must collect are:
> - `title` (text, at least 3 characters)
> - `description` (text, at least 10 characters)
> - `property_type` (text — must be one of: house, apartment, land, commercial, townhouse, villa, cottage, penthouse, studio)
> - `listing_type` (text — must be exactly: sale or rent)
> - `price` (number — must be greater than 0)
> - `location` (text — neighborhood or area, e.g. "Kilimani")
>
> The **optional** fields are: `city` (defaults to "Nairobi" if omitted), `county`, `bedrooms`, `bathrooms`, `square_meters`, `amenities` (list), `furnished` (boolean), `parking_spots`, `has_garden`, `has_swimming_pool`, `pet_friendly`, `gated_community`, `images` (list of image URLs), `video_url`, `virtual_tour_url`, `agent_name`, `agent_phone`, `agent_email`, `source` (e.g. "yourdomain.com").
>
> Then update my property submission form so that when a user fills it out and clicks submit, the form POSTs to my own `/api/submit-property` backend route (not directly to Simon agent's API).
>
> **Feature 2 — Search results page**
>
> Create a frontend search results page. When a visitor selects filters (location, price range, bedrooms, etc.), make a GET request to `https://samantha-nrev.onrender.com/api/properties/` passing the filters as URL query parameters. Display the results in a grid showing: title, price, thumbnail image, bedrooms, bathrooms, location, city, and agent name. Also implement pagination using `limit` and `offset` parameters.
>
> Available search query parameters: `location`, `city`, `property_type` (house, apartment, land, commercial, townhouse, villa, cottage, penthouse, studio), `listing_type` (sale, rent), `min_price`, `max_price`, `bedrooms`, `min_bedrooms`, `min_sqm`, `max_sqm`, `pet_friendly` (true/false), `gated_community` (true/false), `sort_by` (price, bedrooms, square_meters, created_at), `sort_order` (asc, desc), `limit` (1–200), `offset` (integer).
>
> Also create a single-property detail page that fetches from `GET https://samantha-nrev.onrender.com/api/properties/{propertyId}` and displays the full description, all images, agent contact info, and any video/virtual tour links.
>
> **Feature 3 — Simon agent chat bubble**
>
> Add these two blocks of HTML to my site's `<head>` (or just before `</body>`), replacing the placeholder below with the API key value:
>
> ```html
> <!-- 1. Configuration (must come BEFORE the script tag below) -->
> <script>
>   window.SimonChatConfig = {
>     apiBase: "https://samantha-nrev.onrender.com",
>     apiKey: "sk-web-RPW0zl8nX7mCVyArcgE3fy6OZl5k1Aa7dHjxB1Sar-k",
>     title: "Simon agent",
>     brandColor: "#0d6efd",
>     position: "right",
>     welcomeMessage: "Hi! I'm Simon agent — your Kenya real-estate assistant 👋"
>   };
> </script>
> <!-- 2. Load the chat widget -->
> <script src="https://samantha-nrev.onrender.com/static/chat-widget.js"></script>
> ```
>
> That's everything — the chat bubble will appear in the bottom-right corner of every page where these tags are placed.

---

### Reference: what happens after you submit a property

- I upsert your listing into my PostgreSQL database (Supabase). Resubmitting the same listing (matching title + location + price + type + listing_type) just updates it — no duplicates.
- The property is **immediately indexed** into my search system, so it appears in both filtered and natural-language searches within seconds.
- **Success response:**
```json
{ "id": "<uuid>", "status": "created", "title": "Your listing title" }
```

### Reference: what visitors can do with Simon agent

Simon agent is a full AI real-estate assistant. A visitor on your site can ask it to:
- Search the shared property pool by location, price, bedrooms, etc. (structured or natural language)
- See full property details, photos, agent contact info
- Compare properties side by side
- Book a viewing appointment
- Ask market or mortgage questions
- Be handed off to me (the developer) via Telegram notifications

Simon agent sessions are persisted across page reloads (stored in the visitor's browser `localStorage`).

### Reference: building your own chat UI (instead of the widget)

If you prefer full control over the chat UI, call the API directly instead of using the widget:

```
POST https://samantha-nrev.onrender.com/api/chat/
Headers: Content-Type: application/json, X-API-Key: sk-web-RPW0zl8nX7mCVyArcgE3fy6OZl5k1Aa7dHjxB1Sar-k
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

1. **Set the property admin credentials.** ✅ Done — `PROPERTY_ADMIN_USER` and `PROPERTY_ADMIN_PASSWORD` are now set in my Render environment with strong, unique values.

2. **Set the Simon agent web API key.** ✅ Done — `SAMANTHA_WEB_API_KEY` is now set in my Render environment.

3. **Deploy and confirm the API is live.** ✅ Done — the base URL `https://samantha-nrev.onrender.com` is live and all endpoints respond.

4. **Serve the chat widget.** ✅ Done — the widget is already mounted as a static file at `/static/chat-widget.js` via FastAPI in `src/main.py`.

5. **Restrict CORS to your domain.** ✅ Done — `CORS_ALLOWED_ORIGINS` is set to `https://www.realtorroundtables.co.ke/` in my environment.

6. **Monitor and support.** I'll watch Simon agent's logs for any integration errors and help you debug if something doesn't work.

---

## 3. What's Remaining

| # | Item | Who owns it | Status |
|---|---|---|---|
| 1 | `PROPERTY_ADMIN_USER` | I | ✅ Set in Render (`.env`) |
| 2 | `PROPERTY_ADMIN_PASSWORD` | I | ✅ Set in Render (`.env`) |
| 3 | `SAMANTHA_WEB_API_KEY` | I | ✅ Set in Render (`.env`) |
| 4 | `CORS_ALLOWED_ORIGINS` | I | ✅ Set to `https://www.realtorroundtables.co.ke/` |
| 5 | Your website's CORS origin | I | ✅ Confirmed (realtorroundtables.co.ke) |
| 6 | Your property form fields → my API payload mapping | You | ❓ Confirm which fields your form collects with lovable.ai |

---

## Checklist for You

- [ ] Receive `PROPERTY_ADMIN_USER` / `PROPERTY_ADMIN_PASSWORD` from I (see section 1a above).
- [ ] Copy-paste the single lovable.ai prompt from section 1b into lovable.ai.
- [ ] Receive `SAMANTHA_WEB_API_KEY` from I (see section 1a above — value is in the prompt).
- [ ] Paste the two `<script>` tags on your site to embed Simon agent (included in the lovable.ai prompt).
- [ ] Confirm with I that `CORS_ALLOWED_ORIGINS` is set to your domain (`https://www.realtorroundtables.co.ke/`).
- [ ] Test: submit a property from your site and verify it appears in Simon agent's search.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| `401 Unauthorized` when submitting a property | The admin credentials are wrong — ask I to confirm `PROPERTY_ADMIN_USER` / `PROPERTY_ADMIN_PASSWORD`. |
| Property not appearing in search | Wait a few seconds for indexing, or confirm your `POST` returned `{"id": ...}` with HTTP 201. |
| `401` on the chat widget | The `apiKey` in `SimonChatConfig` doesn't match — ask I to confirm `SAMANTHA_WEB_API_KEY`. |
| Chat bubble doesn't appear | Make sure `apiBase` is set in `window.SimonChatConfig` and the `<script src=...>` tag loads **after** it. Check your browser's developer console for errors. |
| Chat returns `503` | Simon agent's AI backend is temporarily unavailable — try again in a minute. |

---

> 📄 For Simon's internal technical reference (endpoint specs, schemas, deployment notes), see [`INTEGRATION.md`](./INTEGRATION.md).
