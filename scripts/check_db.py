"""
check_db — verify that the Supabase project Samantha depends on is reachable,
authenticated, and has the tables/columns the tools expect.

This exists because the four failing agent tools (search_properties,
semantic_search_properties, check_payment_history, save_customer_fact) all
went through Supabase silently, and the failures looked identical from the
logs regardless of *why* they broke:

  - discontinued Supabase project  ->  DNS fails (Name or service not known)
  - resumed project, empty schema   ->  PGRST205 (table missing from schema cache)
  - wrong service_role key          ->  401 / auth errors
  - tables exist but columns differ ->  PGRST204 / schema mismatch on first call

Run this after you resume/migrate a Supabase project and before you redeploy,
so the failure (if any) is loud and specific instead of a generic
"Tool failed during execution" in the WhatsApp bot.

Usage:
    python scripts/check_db.py                 # uses SUPABASE_URL + SUPABASE_KEY from env/.env
    SUPABASE_URL=... SUPABASE_KEY=... python scripts/check_db.py
    python scripts/check_db.py --json          # machine-readable output (exit 0 ok, 1 not ok)

Exit codes:
    0  all checks passed
    1  one or more checks failed (see report)
    2  cannot run (env missing / unhandled error)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

# Ensure the project root is on the path so `src.*` imports work when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger  # noqa: E402

# We import settings first so load_dotenv() runs (same path the app uses),
# then build a FRESH supabase client. We do NOT reuse src.clients.supabase_client
# because that module sets `supabase = None` silently when creds are missing —
# and we want to report that loudly, not silently.
from src.configs import settings  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Expected schema — kept in sync with SQl/schema.sql.
# If you change the schema, update this table and re-run check_db.
# ─────────────────────────────────────────────────────────────────────────────

EXPECTED: dict[str, list[str]] = {
    "customer_profiles": [
        "whatsapp_id", "preferred_name", "budget_range", "preferred_area",
        "created_at", "updated_at",
    ],
    "mpesa_transactions": [
        "checkout_request_id", "merchant_request_id", "phone_number", "amount",
        "state", "account_reference", "mpesa_receipt", "result_desc",
        "created_at", "updated_at",
    ],
    "properties": [
        "id", "title", "description", "property_type", "listing_type", "status",
        "price", "currency", "price_per_sqm", "bedrooms", "bathrooms",
        "square_meters", "lot_size_sqm", "year_built", "floor_number",
        "total_floors", "location", "city", "county", "latitude", "longitude",
        "amenities", "furnished", "parking_spots", "has_garden",
        "has_swimming_pool", "pet_friendly", "gated_community", "images",
        "video_url", "virtual_tour_url", "agent_name", "agent_phone",
        "agent_email", "source", "external_id", "created_at", "updated_at",
    ],
}


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Checks
# ─────────────────────────────────────────────────────────────────────────────

def check_env() -> CheckResult:
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_KEY
    problems = []
    if not url:
        problems.append("SUPABASE_URL is empty/unset")
    elif not url.startswith("https://") or ".supabase.co" not in url:
        problems.append(f"SUPABASE_URL looks malformed: {url!r}")
    if not key:
        problems.append("SUPABASE_KEY is empty/unset")
    elif not key.startswith("eyJ"):
        # Supabase keys (anon + service_role) are JWTs and start with eyJ.
        problems.append("SUPABASE_KEY does not look like a Supabase JWT (expected 'eyJ...')")
    if problems:
        return CheckResult("env", ok=False, detail="; ".join(problems),
                           extra={"url": url, "key_prefix": (key[:8] + "…") if key else None})
    return CheckResult("env", ok=True, detail="SUPABASE_URL + SUPABASE_KEY present and well-formed",
                       extra={"url": url, "key_prefix": key[:8] + "…"})


async def check_reachable() -> CheckResult:
    """TCP/DNS reachability of the Supabase REST host, independent of auth.

    This catches the discontinued-project case (Name or service not known)
    without needing a valid key.
    """
    import httpx

    url = settings.SUPABASE_URL
    host = url.replace("https://", "").split("/")[0]
    try:
        # We don't care about the HTTP status — even a 404/401 proves DNS + TCP work.
        async with httpx.AsyncClient(timeout=10.0) as c:
            await c.get(f"https://{host}/rest/v1/", headers={"apikey": "x"})
    except httpx.ConnectError as e:
        return CheckResult("reachable", ok=False,
                           detail=f"DNS/TCP failure: {e}. The Supabase project may be discontinued or the network is blocked.",
                           extra={"host": host})
    except Exception as e:
        # Timeouts etc. are still connectivity problems worth surfacing.
        return CheckResult("reachable", ok=False, detail=f"{type(e).__name__}: {e}",
                           extra={"host": host})
    return CheckResult("reachable", ok=True, detail=f"Host {host} is DNS-resolvable and accepting TCP connections.",
                       extra={"host": host})


async def check_tables(supabase) -> list[CheckResult]:
    """Confirm each expected table exists and has the expected columns.

    We list-zero rows from each table. A PGRST205 ('table not in schema cache')
    or 404 means the table is missing; a PGRST204 means a column is missing.
    We don't query by every expected column at once (that would mask *which*
    one is missing) — we head-select the expected columns so the first
    mismatched column names itself in the error.
    """
    results: list[CheckResult] = []
    for table, columns in EXPECTED.items():
        cols_csv = ",".join(columns)
        try:
            await supabase.table(table).select(cols_csv).limit(1).execute()
        except Exception as e:
            name = type(e).__name__
            msg = str(e)
            # PGRST205 = table missing; PGRST204 = column missing. Surface both.
            results.append(CheckResult(f"table:{table}", ok=False,
                                       detail=f"{name}: {msg}",
                                       extra={"columns": columns}))
        else:
            results.append(CheckResult(f"table:{table}", ok=True,
                                       detail=f"Table exists and exposes {len(columns)} expected columns.",
                                       extra={"columns": columns}))
    return results


async def check_rowcounts(supabase) -> list[CheckResult]:
    """Report row counts so you know whether the table is created-but-empty.

    Empty `properties` is a common gotcha: the schema is correct, but
    search returns nothing because nobody ran scripts/seed_properties.py.
    We flag that distinctly.
    """
    results: list[CheckResult] = []
    for table in EXPECTED:
        try:
            r = await supabase.table(table).select("id" if table == "properties" else "*",
                                                     count="exact").limit(1).execute()
            count = r.count if hasattr(r, "count") and r.count is not None else "unknown"
        except Exception as e:
            results.append(CheckResult(f"rows:{table}", ok=False, detail=f"{type(e).__name__}: {e}"))
            continue
        # We can't always read count via the client; fall back to len(data).
        n = len(r.data) if hasattr(r, "data") and r.data is not None else 0
        results.append(CheckResult(f"rows:{table}", ok=True,
                                   detail=f"-readable, sample returned {n} row(s)" + (
                                       "  ⚠ empty — run scripts/seed_properties.py for `properties`" if table == "properties" and n == 0 else ""),
                                   extra={"count": count, "sample": n}))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────

async def run_all() -> list[CheckResult]:
    results: list[CheckResult] = [check_env()]
    env = results[0]
    if not env.ok:
        # If env is wrong, the rest can't run meaningfully — but still try
        # reachability, which only needs the URL.
        pass

    # Build a client. We import lazily so a broken supabase-py install doesn't
    # hide the env check.
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        results.append(CheckResult("client", ok=False, detail="cannot build client: env missing"))
        # still try reachability with just the URL if present
        if settings.SUPABASE_URL:
            results.append(await check_reachable())
        return results

    try:
        from supabase import create_client
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    except Exception as e:
        results.append(CheckResult("client", ok=False, detail=f"create_client failed: {type(e).__name__}: {e}"))
        results.append(await check_reachable())
        return results

    results.append(CheckResult("client", ok=True, detail="supabase client constructed"))
    results.append(await check_reachable())
    if results[-1].ok:
        results.extend(await check_tables(supabase))
        results.extend(await check_rowcounts(supabase))
    else:
        results.append(CheckResult("tables", ok=False, detail="skipped — host unreachable"))
        results.append(CheckResult("rows", ok=False, detail="skipped — host unreachable"))
    return results


def render_plain(results: list[CheckResult]) -> str:
    lines = []
    ok_all = all(r.ok for r in results)
    lines.append("✅ ALL CHECKS PASSED" if ok_all else "❌ SOME CHECKS FAILED")
    lines.append("")
    for r in results:
        mark = "✅" if r.ok else "❌"
        lines.append(f"{mark} {r.name:<24} {r.detail}")
    lines.append("")
    lines.append("Verdict: " + ("Samantha's Supabase-backed tools should work." if ok_all
                                else "Fix the ❌ items above, then re-run this script."))
    return "\n".join(lines)


def render_json(results: list[CheckResult]) -> str:
    return json.dumps(
        [{"name": r.name, "ok": r.ok, "detail": r.detail, "extra": r.extra} for r in results],
        indent=2,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--quiet", action="store_true", help="suppress the per-check log lines")
    args = ap.parse_args()

    results = asyncio.run(run_all())

    if args.json:
        print(render_json(results))
    else:
        print(render_plain(results))

    if not args.quiet and not args.json:
        for r in results:
            if r.ok:
                logger.info("✅ {} — {}", r.name, r.detail)
            else:
                logger.error("❌ {} — {}", r.name, r.detail)

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:
        # Unexpected blowup → exit 2 so automation can distinguish infra-broken
        # (exit 1, reported cleanly) from script-broken (exit 2).
        logger.exception("check_db crashed: {}", e)
        raise SystemExit(2)
