-- ============================================================================
-- Samantha Real Estate — Production Database Schema
-- Target: Supabase PostgreSQL 15+
-- ============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- ENUM TYPES
-- ============================================================================

DO $$ BEGIN
    CREATE TYPE property_type AS ENUM (
        'house', 'apartment', 'land', 'commercial',
        'townhouse', 'villa', 'cottage', 'penthouse', 'studio'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE listing_type AS ENUM ('sale', 'rent');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE property_status AS ENUM ('available', 'pending', 'sold', 'rented', 'off_market');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================================
-- PROPERTIES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS properties (
    -- Identity
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Core listing info
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    property_type   property_type NOT NULL,
    listing_type    listing_type NOT NULL,
    status          property_status NOT NULL DEFAULT 'available',

    -- Pricing
    price           NUMERIC NOT NULL CHECK (price > 0),
    currency        TEXT NOT NULL DEFAULT 'KES',
    price_per_sqm   NUMERIC GENERATED ALWAYS AS (
                        CASE WHEN square_meters > 0
                             THEN ROUND(price / square_meters, 2)
                             ELSE NULL
                        END
                    ) STORED,

    -- Physical attributes
    bedrooms        INTEGER CHECK (bedrooms >= 0),
    bathrooms       INTEGER CHECK (bathrooms >= 0),
    square_meters   NUMERIC CHECK (square_meters > 0),
    lot_size_sqm    NUMERIC CHECK (lot_size_sqm > 0),
    year_built      INTEGER CHECK (year_built >= 1900 AND year_built <= 2100),
    floor_number    INTEGER,
    total_floors    INTEGER,

    -- Location
    location        TEXT NOT NULL,       -- neighborhood / area (e.g. "Kilimani")
    city            TEXT NOT NULL DEFAULT 'Nairobi',
    county          TEXT,
    latitude        NUMERIC,
    longitude       NUMERIC,

    -- Features
    amenities       TEXT[] DEFAULT '{}',  -- e.g. {pool,gym,parking,garden,security}
    furnished       BOOLEAN DEFAULT FALSE,
    parking_spots   INTEGER DEFAULT 0,
    has_garden      BOOLEAN DEFAULT FALSE,
    has_swimming_pool BOOLEAN DEFAULT FALSE,
    pet_friendly    BOOLEAN DEFAULT FALSE,
    gated_community BOOLEAN DEFAULT FALSE,

    -- Media
    images          TEXT[] DEFAULT '{}',
    video_url       TEXT,
    virtual_tour_url TEXT,

    -- Contact
    agent_name      TEXT,
    agent_phone     TEXT,
    agent_email     TEXT,

    -- Metadata
    source          TEXT,                -- where the listing came from
    external_id     TEXT,                -- ID from external MLS/CRM
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- B-tree indexes for exact/range lookups
CREATE INDEX IF NOT EXISTS idx_properties_type       ON properties (property_type);
CREATE INDEX IF NOT EXISTS idx_properties_listing    ON properties (listing_type);
CREATE INDEX IF NOT EXISTS idx_properties_status     ON properties (status);
CREATE INDEX IF NOT EXISTS idx_properties_price      ON properties (price);
CREATE INDEX IF NOT EXISTS idx_properties_bedrooms   ON properties (bedrooms);
CREATE INDEX IF NOT EXISTS idx_properties_bathrooms  ON properties (bathrooms);
CREATE INDEX IF NOT EXISTS idx_properties_sqm        ON properties (square_meters);
CREATE INDEX IF NOT EXISTS idx_properties_location   ON properties (location);
CREATE INDEX IF NOT EXISTS idx_properties_city       ON properties (city);

-- Composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_properties_type_listing_price
    ON properties (property_type, listing_type, price);

CREATE INDEX IF NOT EXISTS idx_properties_city_location
    ON properties (city, location);

CREATE INDEX IF NOT EXISTS idx_properties_beds_price
    ON properties (bedrooms, price);

-- GIN index for array columns (amenities, images)
CREATE INDEX IF NOT EXISTS idx_properties_amenities
    ON properties USING GIN (amenities);

-- Partial index for active listings only (most queries filter on this)
CREATE INDEX IF NOT EXISTS idx_properties_active
    ON properties (price, bedrooms, city)
    WHERE status = 'available';

-- ============================================================================
-- UPDATED_AT TRIGGER
-- ============================================================================

CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_properties_updated_at ON properties;
CREATE TRIGGER trg_properties_updated_at
    BEFORE UPDATE ON properties
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_column();

-- ============================================================================
-- CUSTOMER PROFILES (unchanged from original)
-- ============================================================================

CREATE TABLE IF NOT EXISTS customer_profiles (
    whatsapp_id     TEXT PRIMARY KEY,
    preferred_name  TEXT,
    budget_range    TEXT,
    preferred_area  TEXT,
    -- Catch-all for any other customer fact the agent learns (preferred_city,
    -- preferred_bedrooms, preferred_property_type, max_budget_kes, ...).
    -- save_customer_fact accepts any snake_case field; fields that aren't a
    -- real column above are stored here so the upsert never fails with
    -- "column does not exist".
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_customer_profiles_modified_at ON customer_profiles;
CREATE TRIGGER trg_customer_profiles_modified_at
    BEFORE UPDATE ON customer_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_column();

-- ============================================================================
-- MPESA TRANSACTIONS (unchanged from original)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mpesa_transactions (
    checkout_request_id     TEXT PRIMARY KEY,
    merchant_request_id     TEXT,
    phone_number            TEXT,
    amount                  NUMERIC,
    state                   TEXT,
    account_reference       TEXT,
    mpesa_receipt           TEXT,
    result_desc             TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_mpesa_transactions_modified_at ON mpesa_transactions;
CREATE TRIGGER trg_mpesa_transactions_modified_at
    BEFORE UPDATE ON mpesa_transactions
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_column();