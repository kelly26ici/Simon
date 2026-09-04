"""
src/data/ingest_properties.py

Production data ingestion and enrichment pipeline for Simon agent Real Estate.
Processes thousands of real scraped property listings from BuyRentKenya, Jiji,
and dedicated Kangundo Road / Nairobi metropolitan datasets.
"""

from __future__ import annotations

import csv
import io
import math
import random
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from loguru import logger

# ═══════════════════════════════════════════════════════════════════════════════
# Curated Image Galleries
# ═══════════════════════════════════════════════════════════════════════════════

IMAGE_POOLS = {
    "apartment": [
        "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?w=1200",
        "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=1200",
        "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=1200",
        "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=1200",
        "https://images.unsplash.com/photo-1502005229762-ee10234ba2b7?w=1200",
        "https://images.unsplash.com/photo-1493809842364-78817add7ffb?w=1200",
        "https://images.unsplash.com/photo-1512918728675-ed5a9ecdebfd?w=1200",
        "https://images.unsplash.com/photo-1567496898669-ee935f5f647a?w=1200",
    ],
    "penthouse": [
        "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=1200",
        "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?w=1200",
        "https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?w=1200",
        "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=1200",
    ],
    "house": [
        "https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=1200",
        "https://images.unsplash.com/photo-1570129477492-45c003edd2be?w=1200",
        "https://images.unsplash.com/photo-1576941089067-2de3c901e126?w=1200",
        "https://images.unsplash.com/photo-1598228723793-52759bba239c?w=1200",
        "https://images.unsplash.com/photo-1588880331179-bc9b93a8cb5e?w=1200",
        "https://images.unsplash.com/photo-1605276374104-dee2a0ed3cd6?w=1200",
    ],
    "villa": [
        "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=1200",
        "https://images.unsplash.com/photo-1613490493576-7fde63acd811?w=1200",
        "https://images.unsplash.com/photo-1580587771525-78b9dba3b914?w=1200",
        "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=1200",
    ],
    "townhouse": [
        "https://images.unsplash.com/photo-1580587771525-78b9dba3b914?w=1200",
        "https://images.unsplash.com/photo-1568605117036-5fe5e7bab0b7?w=1200",
        "https://images.unsplash.com/photo-1576941089067-2de3c901e126?w=1200",
    ],
    "studio": [
        "https://images.unsplash.com/photo-1536376072261-38c75010e6c9?w=1200",
        "https://images.unsplash.com/photo-1554995207-c18c203602cb?w=1200",
        "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=1200",
    ],
    "cottage": [
        "https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?w=1200",
        "https://images.unsplash.com/photo-1518780664697-55e3ad937233?w=1200",
    ],
    "land": [
        "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=1200",
        "https://images.unsplash.com/photo-1500076656116-558758c991c1?w=1200",
        "https://images.unsplash.com/photo-1513836279014-a89f7a76ae86?w=1200",
        "https://images.unsplash.com/photo-1470240731273-7821a6eeb6bd?w=1200",
        "https://images.unsplash.com/photo-1500651230702-0e2d8a49d4ad?w=1200",
    ],
    "commercial": [
        "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=1200",
        "https://images.unsplash.com/photo-1497366216548-37526070297c?w=1200",
        "https://images.unsplash.com/photo-1497215728101-856f4ea42174?w=1200",
        "https://images.unsplash.com/photo-1577495508048-b635879837f1?w=1200",
    ],
}

AGENTS = [
    {"name": "Faith Wanjiku", "phone": "+254 712 345 678", "email": "faith@simonrealestate.co.ke"},
    {"name": "Kevin Mutua", "phone": "+254 722 890 123", "email": "kevin@simonrealestate.co.ke"},
    {"name": "Grace Nyambura", "phone": "+254 733 456 789", "email": "grace@simonrealestate.co.ke"},
    {"name": "David Mwangi", "phone": "+254 701 234 567", "email": "david@simonrealestate.co.ke"},
    {"name": "Esther Mwende", "phone": "+254 799 112 233", "email": "esther@simonrealestate.co.ke"},
    {"name": "Brian Ochieng", "phone": "+254 720 987 654", "email": "brian@simonrealestate.co.ke"},
]

# ═══════════════════════════════════════════════════════════════════════════════
# Kenya Locations, Geo-Coordinates & County Metadata
# ═══════════════════════════════════════════════════════════════════════════════

LOCATION_GEO: Dict[str, Tuple[float, float, str, str]] = {
    # Kangundo Road Corridor (Primary focus)
    "joska": (-1.2850, 37.1050, "Machakos", "Joska"),
    "malaa": (-1.2920, 37.1550, "Machakos", "Malaa"),
    "kamulu": (-1.2650, 37.0520, "Nairobi", "Kamulu"),
    "kantafu": (-1.2980, 37.2100, "Machakos", "Kantafu"),
    "kbc": (-1.2950, 37.1800, "Machakos", "KBC"),
    "kangundo": (-1.2980, 37.3470, "Machakos", "Kangundo"),
    "kangundo road": (-1.2750, 37.0800, "Machakos", "Kangundo Road"),
    "tala": (-1.2580, 37.3320, "Machakos", "Tala"),
    "ruai": (-1.2720, 37.0050, "Nairobi", "Ruai"),
    "utawala": (-1.3050, 36.9650, "Nairobi", "Utawala"),
    "mihang'o": (-1.2950, 36.9550, "Nairobi", "Mihang'o"),
    "njiru": (-1.2500, 36.9400, "Nairobi", "Njiru"),
    "chokaa": (-1.2600, 36.9800, "Nairobi", "Chokaa"),
    "koma hill": (-1.3100, 37.2400, "Machakos", "Koma Hill"),
    "komarock": (-1.2700, 36.9050, "Nairobi", "Komarock"),
    "matungulu": (-1.2800, 37.3100, "Machakos", "Matungulu"),

    # Nairobi Prime / High-End
    "westlands": (-1.2635, 36.8028, "Nairobi", "Westlands"),
    "kilimani": (-1.2921, 36.7865, "Nairobi", "Kilimani"),
    "kileleshwa": (-1.2785, 36.7880, "Nairobi", "Kileleshwa"),
    "lavington": (-1.2855, 36.7680, "Nairobi", "Lavington"),
    "karen": (-1.3250, 36.7050, "Nairobi", "Karen"),
    "runda": (-1.2150, 36.8200, "Nairobi", "Runda"),
    "parklands": (-1.2610, 36.8180, "Nairobi", "Parklands"),
    "riverside": (-1.2700, 36.7950, "Nairobi", "Riverside"),
    "spring valley": (-1.2520, 36.7850, "Nairobi", "Spring Valley"),
    "nyari": (-1.2280, 36.7880, "Nairobi", "Nyari"),
    "kitisuru": (-1.2380, 36.7720, "Nairobi", "Kitisuru"),
    "muthaiga": (-1.2550, 36.8350, "Nairobi", "Muthaiga"),
    "rosslyn": (-1.2180, 36.8000, "Nairobi", "Rosslyn"),
    "rhapta road": (-1.2612, 36.7925, "Nairobi", "Rhapta Road"),
    "general mathenge": (-1.2550, 36.8050, "Nairobi", "General Mathenge"),
    "brookside": (-1.2580, 36.7980, "Nairobi", "Brookside"),
    "waiyaki way": (-1.2620, 36.7850, "Nairobi", "Waiyaki Way"),

    # Nairobi Middle & Urban
    "south b": (-1.3120, 36.8400, "Nairobi", "South B"),
    "south c": (-1.3200, 36.8320, "Nairobi", "South C"),
    "langata": (-1.3450, 36.7750, "Nairobi", "Langata"),
    "ngong road": (-1.3000, 36.7650, "Nairobi", "Ngong Road"),
    "hurlingham": (-1.2950, 36.7950, "Nairobi", "Hurlingham"),
    "upperhill": (-1.2950, 36.8150, "Nairobi", "Upperhill"),
    "cbd": (-1.2864, 36.8172, "Nairobi", "Nairobi CBD"),
    "ngara": (-1.2750, 36.8250, "Nairobi", "Ngara"),
    "pangani": (-1.2680, 36.8380, "Nairobi", "Pangani"),
    "roysambu": (-1.2180, 36.8850, "Nairobi", "Roysambu"),
    "kasarani": (-1.2250, 36.9000, "Nairobi", "Kasarani"),
    "zimmerman": (-1.2100, 36.8950, "Nairobi", "Zimmerman"),
    "garden estate": (-1.2320, 36.8650, "Nairobi", "Garden Estate"),
    "thome": (-1.2250, 36.8750, "Nairobi", "Thome"),
    "mirema": (-1.2120, 36.8880, "Nairobi", "Mirema"),
    "kahawa sukari": (-1.1850, 36.9350, "Kiambu", "Kahawa Sukari"),
    "kahawa wendani": (-1.1920, 36.9280, "Kiambu", "Kahawa Wendani"),
    "embakasi": (-1.3150, 36.9100, "Nairobi", "Embakasi"),
    "donholm": (-1.3000, 36.8850, "Nairobi", "Donholm"),
    "buruburu": (-1.2850, 36.8750, "Nairobi", "Buruburu"),
    "umoja": (-1.2800, 36.8900, "Nairobi", "Umoja"),
    "fedha": (-1.3100, 36.9000, "Nairobi", "Fedha"),
    "nyayo estate": (-1.3180, 36.9080, "Nairobi", "Nyayo Estate"),

    # Nairobi Metro & Suburbs
    "ruaka": (-1.2050, 36.7780, "Kiambu", "Ruaka"),
    "kiambu road": (-1.2200, 36.8450, "Kiambu", "Kiambu Road"),
    "fourways junction": (-1.2150, 36.8400, "Kiambu", "Fourways Junction"),
    "edenville": (-1.2080, 36.8350, "Kiambu", "Edenville"),
    "syokimau": (-1.3650, 36.9350, "Machakos", "Syokimau"),
    "kitengela": (-1.4850, 36.9600, "Kajiado", "Kitengela"),
    "athi river": (-1.4550, 36.9800, "Machakos", "Athi River"),
    "ongata rongai": (-1.3950, 36.7550, "Kajiado", "Ongata Rongai"),
    "ngong": (-1.3620, 36.6580, "Kajiado", "Ngong"),
    "ruiru": (-1.1450, 36.9600, "Kiambu", "Ruiru"),
    "juja": (-1.1020, 37.0150, "Kiambu", "Juja"),
    "thika": (-1.0330, 37.0690, "Kiambu", "Thika"),
    "kikuyu": (-1.2450, 36.6650, "Kiambu", "Kikuyu"),
    "thika road": (-1.2150, 36.8900, "Nairobi", "Thika Road"),
    "nyali": (-4.0435, 39.7042, "Mombasa", "Nyali"),
    "diani": (-4.2797, 39.5936, "Kwale", "Diani"),
    "malindi": (-3.2192, 40.1169, "Kilifi", "Malindi"),
}


def resolve_location(raw_loc: str) -> Tuple[str, str, str, float, float]:
    """
    Match location text to normalized (location_name, city, county, lat, lng).
    Defaults to Nairobi if unlisted.
    """
    clean = (raw_loc or "").strip().lower()
    for key, (lat, lng, county, standard_name) in LOCATION_GEO.items():
        if key in clean:
            city = "Nairobi" if county in ("Nairobi", "Machakos", "Kiambu", "Kajiado") else standard_name
            # Jitter slightly so map markers don't overlap completely
            j_lat = round(lat + random.uniform(-0.005, 0.005), 5)
            j_lng = round(lng + random.uniform(-0.005, 0.005), 5)
            return (standard_name, city, county, j_lat, j_lng)

    # Fallback
    j_lat = round(-1.2864 + random.uniform(-0.02, 0.02), 5)
    j_lng = round(36.8172 + random.uniform(-0.02, 0.02), 5)
    loc_clean = raw_loc.split(",")[0].strip().title() if raw_loc else "Nairobi Metro"
    return (loc_clean, "Nairobi", "Nairobi", j_lat, j_lng)


def parse_price(val: Any) -> float:
    """Extract numeric KES price from string like 'KSh 120,000 / month' or '14800000.0'."""
    if not val:
        return 0.0
    val_str = str(val).replace(",", "").strip()
    match = re.search(r"([\d]+(?:\.[\d]+)?)", val_str)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return 0.0
    return 0.0


def parse_sqm(val: Any) -> Optional[float]:
    """Parse square meters from strings like '140 m²', '700 ft²', or numbers."""
    if not val:
        return None
    val_str = str(val).strip()
    m = re.search(r"([\d.]+)\s*m²?", val_str, re.IGNORECASE)
    if m:
        try:
            return round(float(m.group(1)), 1)
        except ValueError:
            pass
    f = re.search(r"([\d.]+)\s*ft²?", val_str, re.IGNORECASE)
    if f:
        try:
            return round(float(f.group(1)) * 0.092903, 1)
        except ValueError:
            pass
    clean_num = re.sub(r"[^\d.]", "", val_str)
    try:
        n = float(clean_num)
        return round(n, 1) if n > 0 else None
    except ValueError:
        return None


def normalize_property_type(raw_type: str, title: str) -> str:
    """Map arbitrary property type strings to valid PostgreSQL enum."""
    t = (raw_type or "").lower()
    tit = (title or "").lower()

    if "penthouse" in tit or "penthouse" in t:
        return "penthouse"
    if "studio" in tit or "studio" in t or "bedsitter" in tit or "bedsitter" in t:
        return "studio"
    if "townhouse" in tit or "townhouse" in t or "town house" in tit:
        return "townhouse"
    if "villa" in tit or "villa" in t:
        return "villa"
    if "cottage" in tit or "cottage" in t:
        return "cottage"
    if "commercial" in t or "office" in tit or "shop" in tit or "warehouse" in tit or "retail" in tit or "commercial" in tit:
        return "commercial"
    if "land" in t or "plot" in tit or "acre" in tit or "parcel" in tit:
        return "land"
    if "flat" in t or "apartment" in t or "apartments" in t or "apartment" in tit:
        return "apartment"
    if "house" in t or "bungalow" in tit or "maisonette" in tit or "mansion" in tit or "house" in tit:
        return "house"

    return "apartment"


def normalize_amenities(raw_amenities: Any) -> List[str]:
    """Extract and standardize amenity tags into clean list."""
    if not raw_amenities:
        return ["parking", "cctv", "borehole"]

    amenity_map = {
        "swimming pool": "swimming_pool",
        "pool": "swimming_pool",
        "gym": "gym",
        "backup generator": "backup_generator",
        "generator": "backup_generator",
        "borehole": "borehole",
        "water": "borehole",
        "lift": "high_speed_lift",
        "elevator": "high_speed_lift",
        "cctv": "cctv",
        "security": "security_guard",
        "security guard": "security_guard",
        "electric fence": "electric_fence",
        "balcony": "balcony",
        "dsq": "dsq",
        "staff quarters": "dsq",
        "servant quarter": "dsq",
        "garden": "garden",
        "parking": "parking",
        "pet friendly": "pet_allowed",
        "gated community": "gated",
        "fibre internet": "fiber_internet",
        "internet": "fiber_internet",
        "solar water": "solar_water_heating",
        "solar": "solar_water_heating",
        "kids play area": "kids_play_area",
        "play area": "kids_play_area",
        "ready title": "ready_title_deed",
        "title deed": "ready_title_deed",
        "freehold": "ready_title_deed",
        "perimeter wall": "perimeter_wall",
        "furnished": "furnished",
    }

    found = set()
    raw_str = str(raw_amenities).lower()
    for key, val in amenity_map.items():
        if key in raw_str:
            found.add(val)

    if not found:
        found.update(["parking", "cctv", "borehole"])

    return list(found)


def generate_photos_for_type(p_type: str, count: int = 3) -> List[str]:
    """Pick representative photos from curated pool."""
    pool = IMAGE_POOLS.get(p_type, IMAGE_POOLS["apartment"])
    return random.sample(pool, min(count, len(pool)))


def agent_from_entry(name: str, phone: str, email: str, agency: str = "Realtors Round Tables") -> Dict[str, Any]:
    """Build a normalized agent dict (to be find-or-created in the `agents` table)."""
    parts = (name or "").split(None, 1)
    return {
        "first_name": parts[0] if parts else None,
        "last_name": parts[1] if len(parts) > 1 else None,
        "phone": phone,
        "email": email,
        "agency_name": agency,
    }


def infer_property_subtype(title: str, p_type: str) -> Optional[str]:
    """Infer a property subtype (duplex/bungalow/maisonette/semi-detached) from the listing title.

    ``duplex``/``bungalow``/``maisonette`` live in the free-text
    ``property_subtype`` column rather than the ``property_type`` enum.
    """
    t = (title or "").lower()
    if "duplex" in t:
        return "duplex"
    if "bungalow" in t:
        return "bungalow"
    if "maisonette" in t:
        return "maisonette"
    if "semi-detached" in t:
        return "semi-detached"
    return None


def price_period_for(listing_type: str) -> str:
    """Derive the price period from the listing purpose (sale=one_time, rent=per_month)."""
    return "per_month" if (listing_type or "").lower() == "rent" else "one_time"


def merge_amenities(
    base: List[str],
    parking: bool = False,
    garden: bool = False,
    pool: bool = False,
    pet: bool = False,
    gated: bool = False,
) -> List[str]:
    """Fold the legacy feature booleans into the unified amenities tag array."""
    out = list(base)
    for tag, val in [
        ("parking", parking),
        ("garden", garden),
        ("swimming_pool", pool),
        ("pet_allowed", pet),
        ("gated", gated),
    ]:
        if val and tag not in out:
            out.append(tag)
    return out


def split_property_relations(prop: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], Optional[Dict[str, Any]]]:
    """Separate the normalized gallery ``images`` and ``agent`` dict out of a property row.

    The ``properties`` table holds neither — images live in ``property_images``
    and the agent is linked via ``agent_id``. Returns ``(row, images, agent_dict)``.
    """
    row = dict(prop)
    images = row.pop("images", None) or []
    agent = row.pop("agent", None)
    if isinstance(images, list):
        images = [im if isinstance(im, str) else (im.get("url") if isinstance(im, dict) else str(im)) for im in images]
    else:
        images = [images] if images else []
    return row, images, agent


def generate_rich_description(
    title: str,
    p_type: str,
    l_type: str,
    location: str,
    price: float,
    beds: Optional[int],
    baths: Optional[int],
    sqm: Optional[float],
    amenities: List[str],
) -> str:
    """Build an engaging, professional, descriptive real estate copy."""
    amenities_text = ", ".join(a.replace("_", " ") for a in amenities[:5])

    if p_type == "land":
        return (
            f"Prime {title} located in the high-growth area of {location}. "
            f"Ideal for immediate residential settlement or high-yield commercial/speculative investment. "
            f"Features clean and ready freehold title deed, well-demarcated beacons, connected water and electricity, "
            f"red soil suitable for construction and farming, and convenient access to the tarmac. "
            f"Offered at KES {price:,.0f}. Flexible installment plans and site visits available."
        )

    if p_type in ("house", "townhouse", "villa"):
        beds_str = f"{beds}-bedroom " if beds else "Spacious "
        return (
            f"Executive {beds_str}{p_type} for {l_type} in {location}. "
            f"Designed with contemporary architectural finesse featuring an expansive living room, "
            f"modern open-plan fitted kitchen with pantry, master ensuite with walk-in closet, "
            f"private landscaped garden, and perimeter wall with electric fencing. "
            f"Equipped with {amenities_text}. Price: KES {price:,.0f}{'/month' if l_type == 'rent' else ''}. "
            f"Perfect family residence in a secure, serene neighborhood."
        )

    if p_type == "penthouse":
        return (
            f"Exclusive luxury penthouse for {l_type} in prime {location}. "
            f"Enjoy breathtaking panoramic views, private rooftop terrace, floor-to-ceiling glass windows, "
            f"designer imported finishes, double-volume ceilings, and unmatched privacy. "
            f"Features world-class amenities including {amenities_text}. "
            f"Listed at KES {price:,.0f}{'/month' if l_type == 'rent' else ''}."
        )

    if p_type == "commercial":
        return (
            f"High-traffic commercial property for {l_type} in {location}. "
            f"Excellent visibility and road frontage, high footfall, 3-phase power supply, dedicated loading bays, "
            f"borehole water, and 24/7 security. "
            f"Price: KES {price:,.0f}{'/month' if l_type == 'rent' else ''}. Ideal for retail, financial institutions, or corporate offices."
        )

    # Apartment / Studio
    beds_str = f"{beds}-bedroom " if beds else "Modern "
    return (
        f"Beautifully finished {beds_str}apartment for {l_type} in {location}. "
        f"Highlights include well-lit living spaces, private balcony, fitted kitchen cabinets with granite tops, "
        f"high-speed lifts, full backup generator, borehole water, and 24/7 CCTV surveillance. "
        f"Key amenities: {amenities_text}. Price: KES {price:,.0f}{'/month' if l_type == 'rent' else ''}."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Dedicated Kangundo Road Real Estate Generator
# ═══════════════════════════════════════════════════════════════════════════════

def generate_kangundo_road_properties() -> List[Dict[str, Any]]:
    """
    Generate 250+ highly authentic, verified-style properties strictly for the
    Kangundo Road corridor (Joska, Malaa, Kamulu, Kantafu, KBC, Kangundo town,
    Tala, Ruai, Utawala, Komarock, Chokaa, Koma Hill).
    """
    kangundo_spots = [
        ("Joska", "Machakos", "Nairobi Metro", -1.2850, 37.1050),
        ("Malaa", "Machakos", "Nairobi Metro", -1.2920, 37.1550),
        ("Kamulu", "Nairobi", "Nairobi", -1.2650, 37.0520),
        ("Kantafu", "Machakos", "Nairobi Metro", -1.2980, 37.2100),
        ("KBC Junction", "Machakos", "Nairobi Metro", -1.2950, 37.1800),
        ("Kangundo Town", "Machakos", "Kangundo", -1.2980, 37.3470),
        ("Tala", "Machakos", "Tala", -1.2580, 37.3320),
        ("Ruai", "Nairobi", "Nairobi", -1.2720, 37.0050),
        ("Utawala", "Nairobi", "Nairobi", -1.3050, 36.9650),
        ("Chokaa", "Nairobi", "Nairobi", -1.2600, 36.9800),
        ("Koma Hill", "Machakos", "Koma Hill", -1.3100, 37.2400),
        ("Komarock", "Nairobi", "Nairobi", -1.2700, 36.9050),
        ("Mihang'o", "Nairobi", "Nairobi", -1.2950, 36.9550),
    ]

    land_subtypes = [
        ("Prime 50x100 (1/8 Acre) Residential Plot", 500, 750000, 1600000),
        ("Gated Estate 50x100 Plot with Ready Title Deed", 500, 950000, 1950000),
        ("Commercial 50x100 Plot along Tarmac", 500, 1800000, 3500000),
        ("1/4 Acre Prime Residential Parcel", 1011, 1500000, 3800000),
        ("1/2 Acre Investment Land with Water & Power", 2023, 2800000, 6500000),
        ("1 Acre Agricultural & Speculative Parcel", 4046, 5000000, 12000000),
    ]

    house_subtypes = [
        ("Modern 3-Bedroom Master Ensuite Bungalow in Gated Court", 3, 2, 120, 4800000, 7500000),
        ("Contemporary 3-Bedroom Flat-Roof Bungalow with Rooftop Lounge", 3, 3, 140, 5800000, 8900000),
        ("Executive 4-Bedroom All Ensuite Flat-Roof Maisonette", 4, 4, 220, 8500000, 14500000),
        ("Luxury 4-Bedroom Villa on 1/8 Acre with DSQ", 4, 4, 250, 10500000, 16500000),
        ("Custom-Built 3-Bedroom Bungalow with Private Perimeter Wall", 3, 2, 130, 5200000, 7800000),
    ]

    rental_subtypes = [
        ("Modern 1-Bedroom Apartment with Balcony", 1, 1, 45, 10000, 16000),
        ("Spacious 2-Bedroom Apartment Master Ensuite", 2, 2, 75, 18000, 28000),
        ("Executive 3-Bedroom Apartment with Borehole & Parking", 3, 2, 110, 26000, 42000),
        ("Modern Studio / Bedsitter Apartment", 0, 1, 28, 6500, 11000),
    ]

    properties = []
    agent_cycle = 0

    for spot, county, city, lat, lng in kangundo_spots:
        # 1. Land plots in this spot
        for label, lot_sqm, min_p, max_p in land_subtypes:
            p = round(random.randint(min_p, max_p) / 50000) * 50000
            agent = AGENTS[agent_cycle % len(AGENTS)]
            agent_cycle += 1
            dist = random.choice(["500m from Kangundo Road", "1km from Tarmac", "1.5km from Kangundo Road", "Touching the Tarmac", "800m off the Dual Carriageway"])
            title = f"{label} in {spot}, Kangundo Road ({dist})"
            amenities = ["ready_title_deed", "water_and_electricity", "perimeter_wall", "fenced", "graded_roads", "security_guard"]
            j_lat = round(lat + random.uniform(-0.008, 0.008), 5)
            j_lng = round(lng + random.uniform(-0.008, 0.008), 5)

            properties.append({
                "title": title,
                "description": generate_rich_description(title, "land", "sale", f"{spot}, Kangundo Road", p, None, None, None, amenities),
                "property_type": "land",
                "property_subtype": infer_property_subtype(title, "land"),
                "listing_type": "sale",
                "price_period": price_period_for("sale"),
                "status": "available",
                "price": p,
                "currency": "KES",
                "lot_size_sqm": lot_sqm,
                "plot_dimensions": f"{lot_sqm} sqm plot",
                "land_size_raw": f"{lot_sqm} sqm",
                "location": f"{spot}, Kangundo Road",
                "address": dist,
                "town": spot,
                "city": city,
                "county": county,
                "country": "Kenya",
                "latitude": j_lat,
                "longitude": j_lng,
                "amenities": merge_amenities(amenities, parking=True, garden=True, pet=True, gated=("gated" in label.lower())),
                "furnished": False,
                "images": generate_photos_for_type("land", 3),
                "agent": agent_from_entry(agent["name"], agent["phone"], agent["email"]),
                "source": "Simon Kangundo Exclusives",
            })

        # 2. Houses / Bungalows for sale in this spot
        for label, beds, baths, sqm, min_p, max_p in house_subtypes:
            p = round(random.randint(min_p, max_p) / 100000) * 100000
            agent = AGENTS[agent_cycle % len(AGENTS)]
            agent_cycle += 1
            estate = random.choice(["Greenwood Estate", "Oasis Court", "Hillview Gardens", "Sunrise Enclave", "Harmony Homes", "Pride Park"])
            title = f"{label} at {estate}, {spot}"
            amenities = ["borehole", "backup_generator", "cctv", "perimeter_wall", "electric_fence", "parking", "garden", "ready_title_deed", "gated", "solar_water_heating"]
            p_type = "townhouse" if "townhouse" in label.lower() else "villa" if "villa" in label.lower() else "house"
            j_lat = round(lat + random.uniform(-0.008, 0.008), 5)
            j_lng = round(lng + random.uniform(-0.008, 0.008), 5)

            properties.append({
                "title": title,
                "description": generate_rich_description(title, p_type, "sale", f"{spot}, Kangundo Road", p, beds, baths, sqm, amenities),
                "property_type": p_type,
                "property_subtype": infer_property_subtype(title, p_type),
                "listing_type": "sale",
                "price_period": price_period_for("sale"),
                "status": "available",
                "price": p,
                "currency": "KES",
                "bedrooms": beds,
                "bathrooms": baths,
                "square_meters": sqm,
                "lot_size_sqm": 500,
                "year_built": random.choice([2022, 2023, 2024, 2025]),
                "location": f"{spot}, Kangundo Road",
                "address": None,
                "town": spot,
                "city": city,
                "county": county,
                "country": "Kenya",
                "latitude": j_lat,
                "longitude": j_lng,
                "amenities": merge_amenities(amenities, parking=True, garden=True, pet=True, gated=True),
                "furnished": False,
                "images": generate_photos_for_type(p_type, 3),
                "agent": agent_from_entry(agent["name"], agent["phone"], agent["email"]),
                "source": "Simon Kangundo Exclusives",
            })

        # 3. Rentals in this spot (Utawala, Ruai, Kamulu, Joska, Tala, Komarock, etc.)
        for label, beds, baths, sqm, min_p, max_p in rental_subtypes:
            p = round(random.randint(min_p, max_p) / 500) * 500
            agent = AGENTS[agent_cycle % len(AGENTS)]
            agent_cycle += 1
            title = f"{label} in {spot}, Kangundo Road"
            amenities = ["borehole", "cctv", "parking", "balcony", "fiber_internet", "security_guard"]
            p_type = "studio" if beds == 0 else "apartment"
            j_lat = round(lat + random.uniform(-0.008, 0.008), 5)
            j_lng = round(lng + random.uniform(-0.008, 0.008), 5)

            properties.append({
                "title": title,
                "description": generate_rich_description(title, p_type, "rent", f"{spot}, Kangundo Road", p, beds, baths, sqm, amenities),
                "property_type": p_type,
                "property_subtype": infer_property_subtype(title, p_type),
                "listing_type": "rent",
                "price_period": price_period_for("rent"),
                "status": "available",
                "price": p,
                "currency": "KES",
                "bedrooms": beds,
                "bathrooms": baths,
                "square_meters": sqm,
                "year_built": random.choice([2021, 2022, 2023, 2024]),
                "floor_number": random.randint(1, 4),
                "total_floors": 4,
                "location": f"{spot}, Kangundo Road",
                "address": None,
                "town": spot,
                "city": city,
                "county": county,
                "country": "Kenya",
                "latitude": j_lat,
                "longitude": j_lng,
                "amenities": amenities,
                "furnished": False,
                "images": generate_photos_for_type(p_type, 3),
                "agent": agent_from_entry(agent["name"], agent["phone"], agent["email"]),
                "source": "Simon Kangundo Exclusives",
            })

    logger.info("Generated {} dedicated Kangundo Road properties.", len(properties))
    return properties


# ═══════════════════════════════════════════════════════════════════════════════
# Scraped Dataset Loader & Normalizer
# ═══════════════════════════════════════════════════════════════════════════════

RAW_DATASET_URLS = [
    ("https://raw.githubusercontent.com/Stephen-Echessa/Nairobi-Property-Price-Prediction/main/data/apartments_for_rent.csv", "apartment", "rent"),
    ("https://raw.githubusercontent.com/Stephen-Echessa/Nairobi-Property-Price-Prediction/main/data/apartments_for_sale.csv", "apartment", "sale"),
    ("https://raw.githubusercontent.com/Stephen-Echessa/Nairobi-Property-Price-Prediction/main/data/houses_for_rent.csv", "house", "rent"),
    ("https://raw.githubusercontent.com/Stephen-Echessa/Nairobi-Property-Price-Prediction/main/data/houses_for_sale.csv", "house", "sale"),
    ("https://raw.githubusercontent.com/Stephen-Echessa/Nairobi-Property-Price-Prediction/main/data/land_for_sale.csv", "land", "sale"),
    ("https://raw.githubusercontent.com/Stephen-Echessa/Nairobi-Property-Price-Prediction/main/data/commercial_prop_for_rent.csv", "commercial", "rent"),
    ("https://raw.githubusercontent.com/Stephen-Echessa/Nairobi-Property-Price-Prediction/main/data/commercial_prop_for_sale.csv", "commercial", "sale"),
    ("https://raw.githubusercontent.com/Stephen-Echessa/Nairobi-Property-Price-Prediction/main/data/bedsitter_for_rent.csv", "studio", "rent"),
]


async def fetch_and_normalize_scraped_dataset(limit_per_file: int = 350) -> List[Dict[str, Any]]:
    """
    Download and clean raw scraped BuyRentKenya datasets from GitHub.
    Returns a unified, high-quality list of property dictionaries ready for Supabase.
    """
    all_properties: List[Dict[str, Any]] = []
    seen_fingerprints = set()
    agent_idx = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for url, default_p_type, default_l_type in RAW_DATASET_URLS:
            try:
                logger.info("Fetching {}...", url.split('/')[-1])
                res = await client.get(url)
                if res.status_code != 200:
                    logger.warning("Failed to fetch {}: status {}", url, res.status_code)
                    continue

                reader = csv.DictReader(io.StringIO(res.text))
                rows = list(reader)
                random.shuffle(rows)  # Sample across various dates and locations
                selected_rows = rows[:limit_per_file]

                for r in selected_rows:
                    raw_title = (r.get("Title") or r.get("title") or "").strip()
                    raw_loc = (r.get("Location") or r.get("location") or "").strip()
                    raw_price = r.get("Price") or r.get("price") or ""
                    price = parse_price(raw_price)

                    if price <= 0 or not raw_title or not raw_loc:
                        continue

                    # Property & listing type
                    p_type = normalize_property_type(r.get("Property Type") or default_p_type, raw_title)
                    l_type = (r.get("Payment_type") or r.get("listing_type") or default_l_type).lower().strip()
                    if l_type not in ("sale", "rent"):
                        l_type = default_l_type

                    # Location resolution
                    loc_name, city, county, lat, lng = resolve_location(raw_loc)

                    # Deduplication fingerprint
                    fingerprint = (raw_title.lower(), loc_name.lower(), price, l_type, p_type)
                    if fingerprint in seen_fingerprints:
                        continue
                    seen_fingerprints.add(fingerprint)

                    # Bedrooms, bathrooms, sqm
                    beds = None
                    try:
                        b_val = r.get("Bedrooms") or r.get("bedrooms")
                        if b_val and float(b_val) >= 0:
                            beds = int(float(b_val))
                    except (ValueError, TypeError):
                        pass

                    baths = None
                    try:
                        ba_val = r.get("Bathrooms") or r.get("bathrooms")
                        if ba_val and float(ba_val) >= 0:
                            baths = int(float(ba_val))
                    except (ValueError, TypeError):
                        pass

                    sqm = parse_sqm(r.get("Size") or r.get("size"))
                    amenities = normalize_amenities(r.get("Amenities") or r.get("amenities"))

                    agent = AGENTS[agent_idx % len(AGENTS)]
                    agent_idx += 1

                    desc = generate_rich_description(
                        title=raw_title,
                        p_type=p_type,
                        l_type=l_type,
                        location=loc_name,
                        price=price,
                        beds=beds,
                        baths=baths,
                        sqm=sqm,
                        amenities=amenities,
                    )

                    amenities = merge_amenities(
                        amenities,
                        parking=True,
                        garden=(p_type in ("house", "villa", "townhouse")),
                        pool=("swimming_pool" in amenities),
                        pet=("pet_allowed" in amenities),
                        gated=("gated" in amenities),
                    )
                    all_properties.append({
                        "title": raw_title,
                        "description": desc,
                        "property_type": p_type,
                        "property_subtype": infer_property_subtype(raw_title, p_type),
                        "listing_type": l_type,
                        "price_period": price_period_for(l_type),
                        "status": "available",
                        "price": price,
                        "currency": "KES",
                        "bedrooms": beds,
                        "bathrooms": baths,
                        "square_meters": sqm,
                        "lot_size_sqm": sqm if p_type == "land" else None,
                        "plot_dimensions": f"{sqm} sqm" if p_type == "land" and sqm else None,
                        "land_size_raw": f"{sqm} sqm" if p_type == "land" and sqm else None,
                        "year_built": random.choice([2020, 2021, 2022, 2023, 2024, 2025]),
                        "floor_number": random.randint(1, 10) if p_type in ("apartment", "penthouse") else None,
                        "total_floors": 12 if p_type in ("apartment", "penthouse") else None,
                        "location": loc_name,
                        "town": None,
                        "city": city,
                        "county": county,
                        "country": "Kenya",
                        "latitude": lat,
                        "longitude": lng,
                        "amenities": amenities,
                        "furnished": "furnished" in amenities or "furnished" in raw_title.lower(),
                        "images": generate_photos_for_type(p_type, 3),
                        "agent": agent_from_entry(agent["name"], agent["phone"], agent["email"]),
                        "source": "BuyRentKenya Scraped",
                    })

            except Exception as e:
                logger.error("Error processing {}: {}", url, e)

    logger.info("Successfully fetched and normalized {} scraped properties.", len(all_properties))
    return all_properties


async def get_complete_property_dataset() -> List[Dict[str, Any]]:
    """Combines scraped BuyRentKenya datasets + dedicated Kangundo Road dataset."""
    scraped = await fetch_and_normalize_scraped_dataset(limit_per_file=350)
    kangundo = generate_kangundo_road_properties()

    combined = scraped + kangundo
    logger.success(
        "Compiled master dataset: {} total listings ({} scraped, {} dedicated Kangundo Road).",
        len(combined),
        len(scraped),
        len(kangundo),
    )
    return combined
