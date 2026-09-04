"""Tests for seed property data integrity in src/data/seed_properties.py."""

from src.data.seed_properties import PROPERTIES_SEED_DATA

# The new DB model columns + the two denormalized relations the seeder carries
# (`agent` dict and `images` gallery) which get split out on insert. Any key
# outside this set would be a ghost of a removed column.
ALLOWED_SEED_KEYS = {
    "id", "title", "description", "property_type", "property_subtype",
    "listing_type", "price_period", "price", "currency", "price_per_sqm",
    "bedrooms", "bathrooms", "square_meters", "lot_size_sqm", "plot_dimensions",
    "land_size_raw", "year_built", "floor_number", "total_floors",
    "location", "address", "town", "city", "county", "country",
    "latitude", "longitude", "amenities", "furnished", "status",
    "agent", "agent_id", "images", "video_url",
    "source", "external_id", "created_at", "updated_at",
}


def test_seed_properties_not_empty():
    assert len(PROPERTIES_SEED_DATA) > 0


def test_seed_properties_required_fields():
    required_keys = {"title", "description", "property_type", "listing_type", "price", "location", "city"}
    for idx, prop in enumerate(PROPERTIES_SEED_DATA):
        missing = required_keys - set(prop.keys())
        assert not missing, f"Property at index {idx} missing required fields: {missing}"


def test_seed_properties_price_positive():
    for prop in PROPERTIES_SEED_DATA:
        assert prop["price"] > 0, f"Property {prop.get('title')} has invalid price: {prop['price']}"


def test_seed_properties_valid_listing_types():
    valid_listing_types = {"sale", "rent"}
    for prop in PROPERTIES_SEED_DATA:
        assert prop["listing_type"] in valid_listing_types


def test_seed_properties_only_known_columns():
    """Seed rows must not carry any removed/legacy columns (grep-clean guard)."""
    for idx, prop in enumerate(PROPERTIES_SEED_DATA):
        extra = set(prop.keys()) - ALLOWED_SEED_KEYS
        assert not extra, f"Property at index {idx} has unknown/removed columns: {extra}"


def test_seed_properties_have_new_model_fields():
    valid_periods = {"one_time", "per_month", "per_night"}
    for idx, prop in enumerate(PROPERTIES_SEED_DATA):
        assert prop["price_period"] in valid_periods, f"Property {idx} bad price_period: {prop['price_period']}"
        assert prop.get("country") == "Kenya", f"Property {idx} bad country: {prop.get('country')}"
        # price_period must agree with the listing purpose
        expected = "per_month" if prop["listing_type"] == "rent" else "one_time"
        assert prop["price_period"] == expected, (
            f"Property {idx} price_period {prop['price_period']} != expected {expected}"
        )
        # Agent is normalized into a dict (to be find-or-created in `agents`)
        assert "agent" in prop and isinstance(prop["agent"], dict), f"Property {idx} missing agent dict"
        assert prop["agent"].get("phone"), f"Property {idx} agent missing phone"
        # Gallery is a list of image URLs
        assert isinstance(prop.get("images"), list), f"Property {idx} images not a list"


def test_seed_properties_price_period_and_amenities():
    """Rentals are per_month; at least one rental exists in the seed set."""
    rentals = [p for p in PROPERTIES_SEED_DATA if p["listing_type"] == "rent"]
    assert rentals, "expected at least one rental seed property"
    for prop in rentals:
        assert prop["price_period"] == "per_month"
