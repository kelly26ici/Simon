# SQl/sql.py
"""
Database and Vector Store Seeding Script for Simon Real Estate.
Populates Supabase with thousands of verified Kenyan properties (BuyRentKenya +
Kangundo Road + Curated Exclusives) and indexes them into Qdrant.

The property listings are stored in the normalized `properties` table, their
galleries in `property_images`, and their listing agents in `agents` (linked
via `agent_id`). This script splits those relations apart on insert.
"""

import os
import sys
from pathlib import Path
from collections import Counter

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
from loguru import logger

from src.services.db import db
from src.data.ingest_properties import get_complete_property_dataset, split_property_relations
from src.data.seed_properties import PROPERTIES_SEED_DATA
from src.tools.properties import index_all_properties

PROPERTY_FINGERPRINT = "title,location,price,listing_type,property_type,price_period"


def _fingerprint(row: dict) -> tuple:
    return (
        row.get("title"),
        row.get("location"),
        row.get("price"),
        row.get("listing_type"),
        row.get("property_type"),
        row.get("price_period"),
    )


async def seed_all():
    logger.info("Starting Simon comprehensive database seeding...")

    if not db.client:
        logger.error("Supabase client not configured. Check SUPABASE_URL and SUPABASE_KEY in .env")
        return

    # 1. Compile master dataset (Scraped BuyRentKenya + Kangundo Road + Seed Data)
    logger.info("Fetching and normalizing property listings...")
    master_data = await get_complete_property_dataset()

    # Append curated seed exclusives if not already present
    seen_titles = {p.get("title") for p in master_data}
    for p in PROPERTIES_SEED_DATA:
        if p.get("title") not in seen_titles:
            master_data.append(p)
            seen_titles.add(p.get("title"))

    logger.info(f"Total compiled properties to upsert: {len(master_data)}")

    # 2. Split normalized relations (agent + images) and upsert agents once.
    entries = []  # (property_row, images)
    agent_cache: dict = {}
    for p in master_data:
        row, images, agent = split_property_relations(p)
        if agent:
            key = agent.get("phone") or agent.get("email")
            if key and key in agent_cache:
                agent_id = agent_cache[key]
            else:
                arow = await db.upsert_agent(agent)
                agent_id = str(arow["id"]) if arow else None
                if key:
                    agent_cache[key] = agent_id
            if agent_id:
                row["agent_id"] = agent_id
        entries.append((row, images))

    property_rows = [e[0] for e in entries]

    # 3. Batch upsert properties into Supabase PostgreSQL
    logger.info("Batch upserting properties into Supabase PostgreSQL...")
    saved = await db.upsert_properties_batch(
        property_rows,
        batch_size=100,
        on_conflict=PROPERTY_FINGERPRINT,
    )
    saved_count = len(saved)
    logger.success(f"Successfully saved/verified {saved_count} properties in Supabase.")

    # 4. Attach image galleries to the upserted properties (idempotent via unique
    #    (property_id, sort_order) — re-runs update in place).
    by_fingerprint = {_fingerprint(r): r for r in saved}
    attached = 0
    for row, images in entries:
        if not images:
            continue
        match = by_fingerprint.get(_fingerprint(row))
        if match and match.get("id"):
            await db.add_property_images(str(match["id"]), images)
            attached += len(images)
    logger.success(f"Attached {attached} property image records.")

    # 5. Seed developer / test profile
    dev_phone = "254706716616"
    logger.info(f"Setting up developer profile for {dev_phone}...")
    await db.upsert_customer_profile(
        dev_phone,
        {
            "preferred_name": "Rex Kelly",
            "budget_range": "KES 5M - 40M",
            "preferred_area": "Westlands, Kilimani & Kangundo Road",
            "target_property_type": "Apartments, Bungalows & Prime Plots",
            "looking_for": "High ROI investments, residential settlement, and executive living",
        },
    )
    logger.success("Developer profile configured.")

    # 6. Sync & Index with Qdrant
    logger.info("Syncing and indexing all properties into Qdrant vector store...")
    indexed = await index_all_properties()
    logger.success(f"Qdrant indexing complete: {indexed} points indexed.")

    # 7. Print summary report
    types = Counter(p.get("property_type") for p in master_data)
    listings = Counter(p.get("listing_type") for p in master_data)
    locs = Counter(p.get("location") for p in master_data)
    logger.info("=== SEEDING SUMMARY ===")
    logger.info("Property types: {}", dict(types))
    logger.info("Listing types: {}", dict(listings))
    logger.info("Top 10 locations: {}", dict(locs.most_common(10)))


if __name__ == "__main__":
    asyncio.run(seed_all())
