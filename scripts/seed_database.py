# scripts/seed_database.py
"""
Database and Vector Store Seeding Script for Samantha Real Estate.
Populates Supabase with verified properties and indexes them into Qdrant.
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
from loguru import logger

from src.services.db import db
from src.data.seed_properties import PROPERTIES_SEED_DATA
from src.tools.properties import index_all_properties, PROPERTIES_COLLECTION
from src.tools.qdrant import make_collection


async def seed_all():
    logger.info("Starting Samantha database seeding...")

    if not db.client:
        logger.error("Supabase client not configured. Check SUPABASE_URL and SUPABASE_KEY in .env")
        return

    # 1. Seed Properties
    logger.info(f"Seeding {len(PROPERTIES_SEED_DATA)} properties into Supabase...")
    saved_count = 0
    for prop in PROPERTIES_SEED_DATA:
        try:
            res = await db.upsert_property(prop, on_conflict="title,location,price,listing_type,property_type")
            if res:
                saved_count += 1
                logger.info(f"Saved property: {prop['title']}")
        except Exception as e:
            # Fallback if on_conflict constraint differs
            try:
                res = await db.upsert_property(prop)
                if res:
                    saved_count += 1
                    logger.info(f"Saved property (standard upsert): {prop['title']}")
            except Exception as e2:
                logger.warning(f"Failed to seed property {prop['title']}: {e2}")

    logger.success(f"Successfully saved/verified {saved_count} properties in Supabase.")

    # 2. Seed Developer / Test Profile
    dev_phone = "254706716616"
    logger.info(f"Setting up developer profile for {dev_phone}...")
    await db.upsert_customer_profile(
        dev_phone,
        {
            "preferred_name": "Rex Kelly",
            "budget_range": "KES 20M - 40M",
            "preferred_area": "Westlands & Kilimani",
            "target_property_type": "Luxury Apartment / Penthouse",
            "looking_for": "Investment and executive living",
        },
    )
    logger.success("Developer profile configured.")

    # 3. Sync & Index with Qdrant
    logger.info("Syncing and indexing all properties into Qdrant...")
    indexed = await index_all_properties()
    logger.success(f"Qdrant indexing complete: {indexed} points indexed.")


if __name__ == "__main__":
    asyncio.run(seed_all())
