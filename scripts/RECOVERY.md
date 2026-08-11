# Samantha DB Recovery Runbook

When the WhatsApp bot's Supabase-backed tools (`search_properties`,
`semantic_search_properties`, `check_payment_history`, `save_customer_fact`)
start failing, the root cause is almost always one of:

1. **Discontinued / paused Supabase project** — DNS fails
   (`Name or service not known`).
2. **Resumed project, empty schema** — `PGRST205` "Could not find the table
   ... in the schema cache".
3. **Wrong/rotated `SUPABASE_KEY`** — 401 / auth errors.
4. **Empty `properties` table** — schema is correct but search returns nothing
   because nobody seeded it.

## Step 0 — Diagnose

```bash
python scripts/check_db.py
```

Read the ✅/❌ lines. The script tells you exactly which of the four cases
above you're in. Fix the ❌ items, re-run until it says
"ALL CHECKS PASSED".

## Step 1 — Ensure the Supabase project is alive

- Open the Supabase dashboard. If the project is **paused**, click **Restore**.
  (Free-tier projects auto-pause after ~7 days of inactivity.)
- If the project was **deleted**, create a new one and update
  `SUPABASE_URL` + `SUPABASE_KEY` in the **Render environment** (NOT the
  local `.env` — the local file is stale and not what the deploy reads).

## Step 2 — Create the schema

In the Supabase **SQL Editor**, paste the contents of `SQl/schema.sql` and
run it. This creates the three tables the tools depend on:

| Table | Used by |
|---|---|
| `properties` | `search_properties`, `semantic_search_properties` (indirectly, via indexing), `compare_properties` |
| `customer_profiles` | `save_customer_fact`, `get_customer_profile` |
| `mpesa_transactions` | `check_payment_history`, `save_mpesa_transaction`, `get_mpesa_transaction` |

`customer_profiles` has a JSONB `metadata` column — that's intentional.
`save_customer_fact` accepts any snake_case field; fields that aren't a real
column (`preferred_name`/`budget_range`/`preferred_area`) are stored in
`metadata` so the upsert never fails.

## Step 3 — Seed properties (optional but recommended)

Without rows in `properties`, search returns empty results:

```bash
python scripts/seed_properties.py
```

This also indexes the properties into Qdrant for `semantic_search_properties`.

## Step 4 — Set Render env vars and redeploy

In the Render dashboard → your service → Environment, confirm:

- `SUPABASE_URL`   = your project's `https://<ref>.supabase.co`
- `SUPABASE_KEY`   = the **service_role** key (needed for upserts; the anon key is read-only-ish)
- `QDRANT_URL` + `QDRANT_API_KEY`   (for semantic search)
- `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN`   (for embeddings)

Then redeploy.

## Step 5 — Verify end-to-end

After the deploy, on your machine:

```bash
python scripts/check_db.py     # expect: ALL CHECKS PASSED
```

Then send the bot a message that triggers a search, e.g.
*"Show me 3-bedroom apartments in Kilimani under 15 million"*. It should call
`search_properties` and return real rows.

## What is NOT a database problem

These tools worked throughout the outage and don't touch Supabase:

- `web_search`   (Tavily)
- `send_stk_push`, `check_transaction_status`   (Safaricom M-Pesa)

If only those fail while the DB tools work, look at `TAVILY_API_KEY` /
M-Pesa credentials, not Supabase.
