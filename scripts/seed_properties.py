"""
Seed script — inserts a curated sample of Nairobi real estate properties into
Supabase and indexes them in Qdrant for semantic search.

Each listing carries normalized relations: an `agent` dict (find-or-created in
the `agents` table, linked via `agent_id`) and an `images` gallery (stored in
`property_images`). Feature booleans are folded into the `amenities` tag array.

Usage:
    python scripts/seed_properties.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.db import db
from src.tools.properties import index_all_properties
from src.data.ingest_properties import split_property_relations
from loguru import logger


SAMPLE_PROPERTIES = [
{'title': 'Modern 3-Bedroom Apartment in Kilimani',
 'description': 'Spacious modern apartment located in the heart of Kilimani. Features an open-plan '
                'living area, fully fitted kitchen with granite countertops, and large windows '
                'with natural light. The master bedroom has an en-suite bathroom with high-end '
                'fixtures. Complex offers 24/7 security, a swimming pool, gym, and covered '
                'parking. Close to Yaya Centre, hospitals, and schools.',
 'property_type': 'apartment',
 'listing_type': 'sale',
 'status': 'available',
 'price': 18500000,
 'currency': 'KES',
 'bedrooms': 3,
 'bathrooms': 2,
 'square_meters': 180,
 'lot_size_sqm': 250,
 'year_built': 2020,
 'floor_number': 3,
 'total_floors': 5,
 'location': 'Kilimani',
 'city': 'Nairobi',
 'county': 'Nairobi',
 'latitude': -1.2921,
 'longitude': 36.8219,
 'amenities': ['pool', 'gym', 'parking', 'security', 'elevator', 'swimming_pool', 'gated'],
 'furnished': False,
 'source': 'internal',
 'external_id': 'sample-modern-3br-kilimani',
 'price_period': 'one_time',
 'country': 'Kenya',
 'property_subtype': None,
 'agent': {'first_name': 'Samantha',
           'last_name': 'Real Estate',
           'phone': '254700000000',
           'email': 'info@samantha-re.com',
           'agency_name': 'Realtors Round Tables'},
 'images': ['https://example.com/images/kilimani-1.jpg',
            'https://example.com/images/kilimani-2.jpg',
            'https://example.com/images/kilimani-3.jpg']}
,
{'title': 'Luxury 4-Bedroom Townhouse in Westlands',
 'description': 'Elegant four-bedroom townhouse in a secure gated community in Westlands. Features '
                'a spacious lounge with fireplace, modern kitchen with Bosch appliances, and a '
                "private garden. The property includes a domestic wing with two servants' "
                'quarters. Community amenities include a swimming pool, tennis court, and 24/7 '
                'security. Walking distance to Westgate Mall and international schools.',
 'property_type': 'townhouse',
 'listing_type': 'sale',
 'status': 'available',
 'price': 32000000,
 'currency': 'KES',
 'bedrooms': 4,
 'bathrooms': 4,
 'square_meters': 320,
 'lot_size_sqm': 400,
 'year_built': 2019,
 'floor_number': 1,
 'total_floors': 2,
 'location': 'Westlands',
 'city': 'Nairobi',
 'county': 'Nairobi',
 'latitude': -1.2667,
 'longitude': 36.8123,
 'amenities': ['garden',
               'parking',
               'security',
               'tennis_court',
               'pool',
               'swimming_pool',
               'pet_allowed',
               'gated'],
 'furnished': True,
 'source': 'internal',
 'external_id': 'sample-luxury-4br-westlands',
 'price_period': 'one_time',
 'country': 'Kenya',
 'property_subtype': None,
 'agent': {'first_name': 'Samantha',
           'last_name': 'Real Estate',
           'phone': '254700000000',
           'email': 'info@samantha-re.com',
           'agency_name': 'Realtors Round Tables'},
 'images': ['https://example.com/images/westlands-townhouse-1.jpg',
            'https://example.com/images/westlands-townhouse-2.jpg']}
,
{'title': 'Cozy Studio Apartment in Kileleshwa',
 'description': 'Compact and stylish studio apartment perfect for a young professional. Located in '
                'a modern building with 24/7 security and a gym. The open-plan space includes a '
                'kitchenette, sleeping area, and bathroom. Building is close to restaurants, '
                'cafes, and public transport. Ideal for first-time buyers or investors.',
 'property_type': 'studio',
 'listing_type': 'sale',
 'status': 'available',
 'price': 7500000,
 'currency': 'KES',
 'bedrooms': 0,
 'bathrooms': 1,
 'square_meters': 45,
 'lot_size_sqm': None,
 'year_built': 2021,
 'floor_number': 2,
 'total_floors': 6,
 'location': 'Kileleshwa',
 'city': 'Nairobi',
 'county': 'Nairobi',
 'latitude': -1.2536,
 'longitude': 36.8285,
 'amenities': ['gym', 'parking', 'security', 'elevator'],
 'furnished': True,
 'source': 'internal',
 'external_id': 'sample-cozy-studio-kileleshwa',
 'price_period': 'one_time',
 'country': 'Kenya',
 'property_subtype': None,
 'agent': {'first_name': 'Samantha',
           'last_name': 'Real Estate',
           'phone': '254700000000',
           'email': 'info@samantha-re.com',
           'agency_name': 'Realtors Round Tables'},
 'images': ['https://example.com/images/kileleshwa-studio-1.jpg']}
,
{'title': '5-Bedroom Mansion in Muthaiga',
 'description': 'Stunning five-bedroom mansion set on half an acre in the prestigious Muthaiga '
                'area. Features include a grand entrance hall, formal lounge and dining, gourmet '
                'kitchen with wine cellar, home theater, gym, and sauna. The property has a large '
                'garden, swimming pool, and covered parking for 6 cars. Security includes electric '
                'fence, CCTV, and 24/7 guards. One of the most exclusive properties in Nairobi.',
 'property_type': 'house',
 'listing_type': 'sale',
 'status': 'available',
 'price': 125000000,
 'currency': 'KES',
 'bedrooms': 5,
 'bathrooms': 6,
 'square_meters': 850,
 'lot_size_sqm': 4000,
 'year_built': 2015,
 'floor_number': None,
 'total_floors': 2,
 'location': 'Muthaiga',
 'city': 'Nairobi',
 'county': 'Nairobi',
 'latitude': -1.25,
 'longitude': 36.8,
 'amenities': ['garden',
               'pool',
               'parking',
               'security',
               'gym',
               'sauna',
               'theater',
               'wine_cellar',
               'swimming_pool',
               'pet_allowed',
               'gated'],
 'furnished': True,
 'source': 'internal',
 'external_id': 'sample-5br-mansion-muthaiga',
 'price_period': 'one_time',
 'country': 'Kenya',
 'property_subtype': None,
 'agent': {'first_name': 'Samantha',
           'last_name': 'Real Estate',
           'phone': '254700000000',
           'email': 'info@samantha-re.com',
           'agency_name': 'Realtors Round Tables'},
 'images': ['https://example.com/images/muthaiga-1.jpg',
            'https://example.com/images/muthaiga-2.jpg',
            'https://example.com/images/muthaiga-3.jpg']}
,
{'title': '3-Bedroom Apartment for Rent in Lavington',
 'description': 'Well-maintained three-bedroom apartment available for rent in Lavington. The '
                'property features a modern kitchen, spacious living room, and balcony with city '
                'views. Master bedroom has en-suite bathroom. Complex amenities include a swimming '
                "pool, gym, children's play area, and 24/7 security. Close to Lavington Mall and "
                'Green Acres School.',
 'property_type': 'apartment',
 'listing_type': 'rent',
 'status': 'available',
 'price': 180000,
 'currency': 'KES',
 'bedrooms': 3,
 'bathrooms': 2,
 'square_meters': 160,
 'lot_size_sqm': None,
 'year_built': 2018,
 'floor_number': 4,
 'total_floors': 8,
 'location': 'Lavington',
 'city': 'Nairobi',
 'county': 'Nairobi',
 'latitude': -1.2833,
 'longitude': 36.7833,
 'amenities': ['pool',
               'gym',
               'parking',
               'security',
               'playground',
               'elevator',
               'swimming_pool',
               'gated'],
 'furnished': False,
 'source': 'internal',
 'external_id': 'sample-3br-rent-lavington',
 'price_period': 'per_month',
 'country': 'Kenya',
 'property_subtype': None,
 'agent': {'first_name': 'Samantha',
           'last_name': 'Real Estate',
           'phone': '254700000000',
           'email': 'info@samantha-re.com',
           'agency_name': 'Realtors Round Tables'},
 'images': ['https://example.com/images/lavington-rent-1.jpg',
            'https://example.com/images/lavington-rent-2.jpg']}
,
{'title': '2-Bedroom Apartment in Riverside',
 'description': 'Beautiful two-bedroom apartment in the sought-after Riverside area. Features '
                'include a modern kitchen with cabinets, spacious living and dining area, and a '
                'balcony overlooking the river. The complex offers a swimming pool, gym, and 24/7 '
                'security. Walking distance to the river, restaurants, and shopping centers.',
 'property_type': 'apartment',
 'listing_type': 'rent',
 'status': 'available',
 'price': 150000,
 'currency': 'KES',
 'bedrooms': 2,
 'bathrooms': 2,
 'square_meters': 120,
 'lot_size_sqm': None,
 'year_built': 2019,
 'floor_number': 5,
 'total_floors': 10,
 'location': 'Riverside',
 'city': 'Nairobi',
 'county': 'Nairobi',
 'latitude': -1.27,
 'longitude': 36.79,
 'amenities': ['pool', 'gym', 'parking', 'security', 'elevator', 'swimming_pool', 'gated'],
 'furnished': False,
 'source': 'internal',
 'external_id': 'sample-2br-rent-riverside',
 'price_period': 'per_month',
 'country': 'Kenya',
 'property_subtype': None,
 'agent': {'first_name': 'Samantha',
           'last_name': 'Real Estate',
           'phone': '254700000000',
           'email': 'info@samantha-re.com',
           'agency_name': 'Realtors Round Tables'},
 'images': ['https://example.com/images/riverside-2br-1.jpg']}
,
{'title': 'Commercial Property in Upper Hill',
 'description': 'Prime commercial property in Upper Hill, ideal for office use. The building has 8 '
                'floors with approximately 1,200 sqm per floor. Features include a borehole, '
                'backup generator, elevators, and 24/7 security. Located in the central business '
                'district with excellent transport links and proximity to banks and government '
                'offices.',
 'property_type': 'commercial',
 'listing_type': 'sale',
 'status': 'available',
 'price': 85000000,
 'currency': 'KES',
 'bedrooms': None,
 'bathrooms': None,
 'square_meters': 9600,
 'lot_size_sqm': 1200,
 'year_built': 2010,
 'floor_number': None,
 'total_floors': 8,
 'location': 'Upper Hill',
 'city': 'Nairobi',
 'county': 'Nairobi',
 'latitude': -1.29,
 'longitude': 36.82,
 'amenities': ['parking', 'security', 'generator', 'borehole', 'elevator'],
 'furnished': False,
 'source': 'internal',
 'external_id': 'sample-commercial-upper-hill',
 'price_period': 'one_time',
 'country': 'Kenya',
 'property_subtype': None,
 'agent': {'first_name': 'Samantha',
           'last_name': 'Real Estate',
           'phone': '254700000000',
           'email': 'info@samantha-re.com',
           'agency_name': 'Realtors Round Tables'},
 'images': ['https://example.com/images/upper-hill-commercial-1.jpg']}
,
{'title': '4-Bedroom House in Karen',
 'description': 'Charming four-bedroom family home in the leafy suburbs of Karen. Set on a '
                'quarter-acre plot with mature gardens, a swimming pool, and a tennis court. '
                'Features include a spacious lounge with fireplace, modern kitchen, and a '
                'self-contained guest wing. Secure gated community with 24/7 security. Close to '
                'the Giraffe Centre and Karen shopping center.',
 'property_type': 'house',
 'listing_type': 'sale',
 'status': 'available',
 'price': 45000000,
 'currency': 'KES',
 'bedrooms': 4,
 'bathrooms': 3,
 'square_meters': 450,
 'lot_size_sqm': 1000,
 'year_built': 2017,
 'floor_number': None,
 'total_floors': 2,
 'location': 'Karen',
 'city': 'Nairobi',
 'county': 'Nairobi',
 'latitude': -1.37,
 'longitude': 36.68,
 'amenities': ['garden',
               'pool',
               'parking',
               'security',
               'tennis_court',
               'swimming_pool',
               'pet_allowed',
               'gated'],
 'furnished': False,
 'source': 'internal',
 'external_id': 'sample-4br-house-karen',
 'price_period': 'one_time',
 'country': 'Kenya',
 'property_subtype': None,
 'agent': {'first_name': 'Samantha',
           'last_name': 'Real Estate',
           'phone': '254700000000',
           'email': 'info@samantha-re.com',
           'agency_name': 'Realtors Round Tables'},
 'images': ['https://example.com/images/karen-house-1.jpg',
            'https://example.com/images/karen-house-2.jpg']}
,
]


PROPERTY_FINGERPRINT = "title,location,price,listing_type,property_type,price_period"


async def seed():
    """Insert sample properties into Supabase and index into Qdrant."""
    if not db.client:
        logger.error("Supabase client not configured.")
        return
    logger.info("Seeding {} sample properties...", len(SAMPLE_PROPERTIES))

    inserted = 0
    for prop in SAMPLE_PROPERTIES:
        try:
            row, images, agent = split_property_relations(prop)
            if agent:
                arow = await db.upsert_agent(agent)
                if arow:
                    row["agent_id"] = str(arow["id"])
            saved = await db.upsert_property(row, on_conflict=PROPERTY_FINGERPRINT)
            if saved and images:
                await db.add_property_images(str(saved["id"]), images)
            if saved:
                inserted += 1
                logger.success("Seeded: {}", prop["title"])
            else:
                logger.warning("Seed returned no data for: {}", prop["title"])
        except Exception:
            logger.exception("Failed to seed: {}", prop["title"])

    logger.info("Seeding complete for {}/{} properties.", inserted, len(SAMPLE_PROPERTIES))

    logger.info("Indexing into Qdrant...")
    count = await index_all_properties()
    logger.success("Indexed {} properties into Qdrant.", count)


if __name__ == "__main__":
    asyncio.run(seed())
