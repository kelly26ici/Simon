# src/cli.py
"""
Samantha Real Estate CLI Utility.
Manage database, vectors, test agent tools, and run interactive terminal chat.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Optional

from loguru import logger

# Import all tools to ensure registration
import src.tools  # noqa: F401
from src.services.db import db
from src.tools.qdrant import client as qdrant_client, check_if_collection_exists
from src.tools.properties import index_all_properties, semantic_search
from src.tools.embeddings import get_embeddings
from src.messages.chats.conversation import get_history, append_message
from src.messages.chats.text_handler import _build_customer_context_string
from src.services.llm import ask_gpt, MODEL_NAME, _active_provider
from src.data.seed_properties import PROPERTIES_SEED_DATA


async def cmd_status():
    """Check system status and connectivity."""
    print("=" * 60)
    print(" SAMANTHA REAL ESTATE — SYSTEM HEALTH CHECK")
    print("=" * 60)

    # 1. Supabase
    print("\n[1/4] Supabase PostgreSQL Database:")
    if db.client:
        try:
            props = await db.search_properties()
            profiles = await db._run_sync(lambda: db.client.table('customer_profiles').select('whatsapp_id').execute())
            print(f"  ✓ Connected: {len(props)} available properties, {len(profiles.data if profiles else [])} customer profiles")
        except Exception as e:
            print(f"  ✗ Error querying database: {e}")
    else:
        print("  ✗ Client not configured (SUPABASE_URL or SUPABASE_KEY missing)")

    # 2. Qdrant Vector Store
    print("\n[2/4] Qdrant Vector Cloud:")
    try:
        colls = await qdrant_client.get_collections()
        names = [c.name for c in colls.collections]
        if 'properties' in names:
            info = await qdrant_client.get_collection('properties')
            print(f"  ✓ Connected: collection 'properties' active ({info.points_count} points, status={info.status.value})")
        else:
            print("  ! Connected, but 'properties' collection does not exist yet")
    except Exception as e:
        print(f"  ✗ Error connecting to Qdrant: {e}")

    # 3. Embeddings Backend
    print("\n[3/4] Embeddings Service:")
    try:
        vecs = await get_embeddings(["Executive 3-bedroom apartment in Kilimani"])
        if vecs and len(vecs[0]) == 1024:
            print("  ✓ Connected (Cloudflare Workers AI): generated 1024-dim vector")
        else:
            print(f"  ! Unexpected vector dimension: {len(vecs[0]) if vecs else 'empty'}")
    except Exception as e:
        print(f"  ✗ Error generating embeddings: {e}")

    # 4. LLM Service
    print("\n[4/4] LLM Provider:")
    print(f"  ✓ Active provider: {_active_provider.upper()} (Model: {MODEL_NAME})")
    print("=" * 60)


async def cmd_seed():
    """Seed Supabase and Qdrant."""
    print(f"Seeding {len(PROPERTIES_SEED_DATA)} prime properties...")
    saved = 0
    for prop in PROPERTIES_SEED_DATA:
        res = await db.upsert_property(prop, on_conflict="title,location,price,listing_type,property_type")
        if res:
            saved += 1
            print(f"  + {prop['title']}")
    print(f"\nSaved {saved} properties in Supabase.")
    print("Indexing into Qdrant...")
    count = await index_all_properties()
    print(f"Indexed {count} properties into Qdrant collection.")


async def cmd_sync():
    """Sync Supabase listings to Qdrant vectors."""
    print("Syncing all Supabase listings into Qdrant vector store...")
    count = await index_all_properties()
    print(f"✓ Indexed {count} active properties into Qdrant.")


async def cmd_search(query: str, limit: int = 5):
    """Run semantic search from CLI."""
    print(f"Searching for: '{query}' (limit={limit})...\n")
    results = await semantic_search(query=query, limit=limit)
    if not results:
        print("No matching properties found.")
        return

    for idx, r in enumerate(results, 1):
        print(f"{idx}. [{r.get('score', 0):.3f}] {r.get('title')}")
        print(f"   Location: {r.get('location')}, {r.get('city')} | Type: {r.get('property_type')} ({r.get('listing_type')})")
        print(f"   Price: KES {r.get('price'):,.0f} | Beds: {r.get('bedrooms')} | Baths: {r.get('bathrooms')}")
        print(f"   Amenities: {', '.join(r.get('amenities', []))}")
        print(f"   ID: {r.get('id')}\n")


async def cmd_chat(phone: str = "254706716616"):
    """Interactive pair-programming & customer testing terminal chat with Samantha."""
    print("=" * 65)
    print(f" SAMANTHA REAL ESTATE — INTERACTIVE TERMINAL AGENT")
    print(f" Customer Phone Context: {phone}")
    print(f" Type your message below. Type 'exit', 'quit', or 'clear' anytime.")
    print("=" * 65 + "\n")

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Exiting chat. Bye!")
            break
        if user_input.lower() == "clear":
            from src.core.redis import RedisStore
            store = RedisStore(prefix="history")
            await store.set(phone, [])
            print("✓ Conversation history cleared.")
            continue

        await append_message(phone, "user", user_input)
        history = await get_history(phone)
        context = await _build_customer_context_string(phone)

        print("\n[Samantha is thinking & using tools...]\n")
        try:
            response = await ask_gpt(history, customer_context=context)
            output_text = getattr(response, "output_text", "") or "I am having trouble answering right now."
            await append_message(phone, "assistant", output_text)
            print(f"Samantha:\n{output_text}")
        except Exception as e:
            print(f"Samantha encountered an error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Samantha Real Estate CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    subparsers.add_parser("status", help="Check system status and connections")
    subparsers.add_parser("seed", help="Seed database with properties")
    subparsers.add_parser("sync", help="Sync properties to Qdrant vector index")

    search_parser = subparsers.add_parser("search", help="Search properties semantically")
    search_parser.add_argument("query", type=str, help="Search query")
    search_parser.add_argument("--limit", type=int, default=5, help="Result limit")

    chat_parser = subparsers.add_parser("chat", help="Start interactive chat with Samantha")
    chat_parser.add_argument("--phone", type=str, default="254706716616", help="Customer phone/ID")

    args = parser.parse_args()

    if args.command == "status":
        asyncio.run(cmd_status())
    elif args.command == "seed":
        asyncio.run(cmd_seed())
    elif args.command == "sync":
        asyncio.run(cmd_sync())
    elif args.command == "search":
        asyncio.run(cmd_search(args.query, args.limit))
    elif args.command == "chat":
        asyncio.run(cmd_chat(args.phone))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
