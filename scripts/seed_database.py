# scripts/seed_database.py
"""
Database and Vector Store Seeding Script for Samantha Real Estate.
Populates Supabase with thousands of verified Kenyan properties (BuyRentKenya + Kangundo Road + Exclusives)
and indexes them into Qdrant.
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
from src.data.ingest_properties import get_complete_property_dataset
from src.data.seed_properties import PROPERTIES_SEED_DATA
from src.tools.properties import index_all_properties, PROPERTIES_COLLECTION
from src.tools.qdrant import make_collection


async def seed_all():
    logger.info("Starting Samantha comprehensive database seeding...")

    if not db.client:
        logger.error("Supabase client not configured. Check SUPABASE_URL and SUPABASE_KEY in .env")
        return

    # 1. Compile master dataset (Scraped BuyRentKenya + Kangundo Road + Seed Data)
    logger.info("Fetching and normalizing property listings...")
    master_data = await get_complete_property_dataset()

    # Append seed exclusives if not already present
    seen_titles = {p.get("title") for p in master_data}
    for p in PROPERTIES_SEED_DATA:
        if p.get("title") not in seen_titles:
            master_data.append(p)
            seen_titles.add(p.get("title"))

    logger.info(f"Total compiled properties to upsert: {len(master_data)}")

    # 2. Batch upsert into Supabase
    logger.info("Batch upserting properties into Supabase PostgreSQL...")
    saved_count = await db.upsert_properties_batch(
        master_data,
        batch_size=100,
        on_conflict="title,location,price,listing_type,property_type",
    )
    logger.success(f"Successfully saved/verified {saved_count} properties in Supabase.")

    # 3. Seed Developer / Test Profile
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

    # 4. Sync & Index with Qdrant
    logger.info("Syncing and indexing all properties into Qdrant vector store...")
    indexed = await index_all_properties()
    logger.success(f"Qdrant indexing complete: {indexed} points indexed.")

    # 5. Print summary report
    types = Counter(p.get("property_type") for p in master_data)
    listings = Counter(p.get("listing_type") for p in master_data)
    locs = Counter(p.get("location") for p in master_data)
    logger.info("=== SEEDING SUMMARY ===")
    logger.info("Property types: {}", dict(types))
    logger.info("Listing types: {}", dict(listings))
    logger.info("Top 10 locations: {}", dict(locs.most_common(10)))


if __name__ == "__main__":
    asyncio.run(seed_all())

