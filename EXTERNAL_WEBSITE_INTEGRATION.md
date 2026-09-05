# Connect Your Website to Simon Agent (Guide for Simon)

> 👋 **This guide is for you, Simon.**
>
> **Simon agent** is the WhatsApp + website AI real-estate assistant named after
> you. This guide explains, in plain language, how your website connects to it so
> that:
>
> 1. Property listings you add on your website get saved into the shared database.
> 2. Visitors on your website can **search** that same shared database.
> 3. Visitors can **chat with Simon agent** (the AI assistant) in a chat bubble.
>
> You don't need to be a deep programmer. If you build with **lovable.ai** (a
> "vibe coder"), jump straight to **[Section 2](#2--the-one-lovableai-prompt)** —
> there's a single ready-to-paste prompt that builds everything for you.

---

## What "done" means — and what's left for you

The developer has **already completed** the technical side. Here is the current
status so you can see exactly where things stand:

| # | Item | Who did it | Status |
|---|---|---|---|
| 1 | Property admin credentials created | Developer | ✅ Done |
| 2 | Web chat API key created | Developer | ✅ Done |
| 3 | The API is deployed and live | Developer | ✅ Done |
| 4 | The chat widget is hosted and ready | Developer | ✅ Done |
| 5 | Browser access (CORS) restricted to your website | Developer | ✅ Done |
| 6 | Add the chat bubble to your website | **You** | ⬜ Remaining |
| 7 | Connect your property form to the database | **You** | ⬜ Remaining |
| 8 | Add a search page for visitors | **You** | ⬜ Remaining |

Everything you need to do is on **your website's side**, and the lovable.ai prompt
below does most of it automatically.

---

## 1. The connection details you'll use

These are the live values. **Keep them private** — never paste the admin
credentials into browser code or public pages.

| What it's for | Name | Value |
|---|---|---|
| Submit properties to the database | `PROPERTY_ADMIN_USER` | `admin_Xkga15AyFnw` |
| Submit properties to the database | `PROPERTY_ADMIN_PASSWORD` | `GILFJf_9DKFVzh0M8QcaOSuiUQG5E8Od` |
| Let visitors chat with Simon agent | `SAMANTHA_WEB_API_KEY` | `sk-web-RPW0zl8nX7mCVyArcgE3fy6OZl5k1Aa7dHjxB1Sar-k` |

**The API address** (live, confirmed):

```
https://samantha-nrev.onrender.com
```

> ℹ️ **Why does it say "samantha"?** The deployment address and the key name still
> carry the assistant's old working name. They are correct as-is — just don't
> change them in the code.

> ⚠️ **Security rule:** The `PROPERTY_ADMIN_*` credentials must **never** run in
> the visitor's browser. Property *submission* goes through your website's own
> backend (a server-side route). The *search* and *chat widget* are safe to call
> directly from the browser.

---

## 2. — The one lovable.ai prompt

Copy **everything** below (from "I need you to implement" to the end of the
`</script>` tag) and paste it into a new lovable.ai chat. It builds all three
features at once.

> I need you to implement three features on my website that connect to Simon
> agent's API at `https://samantha-nrev.onrender.com`. Please build all three:
>
> **Feature 1 — Backend property submission endpoint**
>
> Create a backend API route on my website at `POST /api/submit-property`. It
> accepts a POST request with JSON and proxies the request to
> `https://samantha-nrev.onrender.com/api/properties/` using HTTP Basic auth with
> username `admin_Xkga15AyFnw` and password `GILFJf_9DKFVzh0M8QcaOSuiUQG5E8Od`.
> Return the API's response back to the caller.
>
> The **required** fields my property form must collect are:
> - `title` (text, at least 3 characters)
> - `description` (text, at least 10 characters)
> - `property_type` (text — must be one of: `house`, `apartment`, `land`,
>   `commercial`, `townhouse`, `villa`, `cottage`, `penthouse`, `studio`)
> - `listing_type` (text — must be exactly `sale` or `rent`)
> - `price` (number, must be greater than 0)
> - `location` (text — the neighborhood or area, e.g. "Kilimani")
>
> The **optional** fields are: `city` (defaults to `Nairobi` if omitted),
> `county`, `country` (defaults to `Kenya`), `town`, `address`,
> `property_subtype` (e.g. "duplex"), `price_period` (`one_time` for sale,
> `per_month` for rent), `bedrooms`, `bathrooms`, `square_meters`,
> `lot_size_sqm`, `plot_dimensions`, `land_size_raw`, `year_built`,
> `floor_number`, `total_floors`, `latitude`, `longitude`, `amenities` (a list
> of feature tags such as `["pool", "garden", "parking", "security"]`),
> `furnished` (boolean), `video_url`, and `source` (e.g. "yourdomain.com").
>
> `images` is a list of image objects, each with a `url` and an optional
> `sort_order` number and `is_featured` boolean, for example
> `[{"url": "https://your-site.com/img/1.jpg", "is_featured": true}]`.
>
> To attach a listing agent, pass an `agent` object with any of:
> `first_name`, `last_name`, `email`, `phone`, `agency_name`, `bio`,
> `avatar_url` — for example
> `"agent": {"first_name": "Realtor", "agency_name": "Realtor Round Tables"}`.
>
> Then update my property submission form so that when a user fills it out and
> clicks submit, the form POSTs to my own `/api/submit-property` backend route
> (not directly to Simon agent's API).
>
> **Feature 2 — Search results page**
>
> Create a frontend search results page. When a visitor selects filters
> (location, price range, bedrooms, etc.), make a GET request to
> `https://samantha-nrev.onrender.com/api/properties/` passing the filters as
> URL query parameters. Display results in a grid showing: title, price,
> thumbnail image, bedrooms, bathrooms, location, city, and agent name. Add
> pagination using `limit` and `offset`.
>
> Available search query parameters: `location`, `town`, `city`, `country`,
> `property_type` (`house`, `apartment`, `land`, `commercial`, `townhouse`,
> `villa`, `cottage`, `penthouse`, `studio`), `listing_type` (`sale`, `rent`),
> `price_period` (`one_time`, `per_month`, `per_night`), `property_subtype`,
> `min_price`, `max_price`, `bedrooms`, `min_bedrooms`, `min_sqm`, `max_sqm`,
> `min_lot_size_sqm`, `max_lot_size_sqm`, `amenities` (a comma-separated list
> of required feature tags — the property must have ALL of them), `furnished`
> (true/false), `sort_by` (`price`, `bedrooms`, `square_meters`, `created_at`),
> `sort_order` (`asc`, `desc`), `limit` (1–200), `offset` (integer).
>
> Also create a single-property detail page that fetches from
> `GET https://samantha-nrev.onrender.com/api/properties/{propertyId}` and
> displays the full description, all images, agent contact info, and any video
> tour link.
>
> **Feature 3 — Simon agent chat bubble**
>
> Add these two blocks of HTML to my site's `<head>` (or just before
> `</body>`). The `apiKey` below is already filled in:
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
> That's everything — the chat bubble will appear in the bottom-right corner of
> every page where these tags are placed.

---

## 3. What happens after you submit a property

- The listing is saved (upserted) into the database. Resubmitting the same
  listing (matching title + location + price + type + listing_type) simply
  **updates** it — no duplicates are created.
- The property is **immediately indexed** into the search system, so it shows up
  in both filtered and natural-language searches within seconds.
- **Success response:**
  ```json
  { "id": "<uuid>", "status": "created", "title": "Your listing title" }
  ```

---

## 4. The database — which tables are used

The database is PostgreSQL, hosted on Supabase. Here is exactly **which tables
exist and what each one holds**:

| Table | What it stores | Used by your website? |
|---|---|---|
| `properties` | The property listings (price, type, location, photos order, features). | ✅ Yes — written on submit, read on search |
| `agents` | Listing agent / agency profiles (name, phone, email, agency). | ✅ Yes — linked to each property |
| `property_images` | Each property's photo gallery (ordered, featured first). | ✅ Yes — attached to listings |
| `property_inquiries` | "Contact us" leads / inquiries from your site. | ✅ Yes — written when a visitor inquires |
| `customer_profiles` | Visitor/customer preferences & memory. | 🔄 Read/write via chat |
| `conversation_messages` | The full chat history (web + WhatsApp). | 🔄 Written by the chat widget |
| `conversation_summaries` | Short summaries of conversations. | 🔄 Via chat |
| `scheduled_viewings` | Booked property viewing appointments. | 🔄 Via chat (booking viewings) |
| `mpesa_transactions` | M-Pesa payment records. | — Not used by the website |
| `bot_settings` | System settings, e.g. the owner's chat ID. | — Not used by the website |

In short: your website **writes** to `properties`, `agents`, `property_images`
(and optionally `property_inquiries`); it **reads** listings from `properties`
with their `property_images` and `agents`; and the **chat widget** writes the
conversation into `conversation_messages` (and can use the viewing/payment
tables when visitors book or pay).

---

## 5. What visitors can do with Simon agent

Simon agent is a full AI real-estate assistant. A visitor on your site can ask
it to:

- Search the shared property pool by location, price, bedrooms, and more
  (structured filters or plain natural language).
- See full property details, photos, and agent contact info.
- Compare properties side by side.
- Book a viewing appointment.
- Ask market or mortgage questions.
- Be handed off to you (the owner) via Telegram notifications.

Chat sessions are remembered across page reloads (stored in the visitor's
browser `localStorage`), so a conversation continues where it left off.

---

## 6. Building your own chat UI (instead of the widget)

If you prefer full control over the look of the chat, you can call the API
directly instead of using the widget:

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

Reuse the returned `session_id` on every subsequent message so the conversation
stays contextual.

---

## 7. Troubleshooting

| Problem | What to do |
|---|---|
| `401 Unauthorized` when submitting a property | The admin credentials are wrong — check `PROPERTY_ADMIN_USER` / `PROPERTY_ADMIN_PASSWORD` in the backend. |
| Property not appearing in search | Wait a few seconds for indexing, or confirm the POST returned `{"id": ...}` with HTTP 201. |
| `401` on the chat widget | The `apiKey` in `SimonChatConfig` doesn't match `SAMANTHA_WEB_API_KEY`. |
| Chat bubble doesn't appear | Make sure `apiBase` is set in `window.SimonChatConfig` and the `<script src=...>` tag loads **after** it. Check the browser's developer console for errors. |
| Chat returns `503` | Simon agent's AI backend is temporarily unavailable — try again in a minute. |
| A field I sent seems to be ignored | Confirm the field name is one of the accepted fields in Section 2. Old names like `has_garden`, `parking_spots`, or `agent_name` are no longer used — use `amenities` and the nested `agent` object instead. |

---

> 📄 For the full technical reference (endpoint specs, field-by-field contract,
> deployment notes), see [`INTEGRATION.md`](./INTEGRATION.md).