-- ============================================================================
-- Property254-Compatible Real Estate Database Schema
-- Target: Supabase PostgreSQL 15+
--
-- Reconstructed public data model of Property254 (https://property254.com),
-- observed via archived listing detail pages (e.g. /property/single/116,
-- /property/single/129) and the WPResidence-powered homepage:
--   * listing purpose:  For Buy (sale) / For Rent / To Let (rent) / short-stay (rent, per-night)
--   * property type:    house, apartment, duplex, villa, land, commercial, studio …
--   * price:            KES amount + price_period (one_time | per_month | per_night)
--   * location:         neighborhood + road/address + town + city + county + country
--   * residential:      bedrooms, bathrooms, square_meters, lot_size_sqm, plot_dimensions,
--                       land_size_raw (preserve "1/4 acre", "50 x 100"), year_built, floors
--   * features:         amenity feature tags (garden, swimming_pool, security, …)
--                       `furnished` kept as a structured descriptor/category
--   * media:            ordered image gallery + featured image (property_images)
--   * agent:            normalized listing-agent profiles (name, phone, email, agency)
--
-- Idempotent: `scripts/migrate.py` runs this file directly via psycopg2 with
-- autocommit. Every statement is safe to re-run on an existing database.
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

-- New enum: how the listing price is charged.
--   one_time  = fixed purchase price          (sale / "For Buy")
--   per_month = monthly rent                  (For Rent / "To Let")
--   per_night = nightly rate                  (Airbnb / short-stay)
DO $$ BEGIN
	CREATE TYPE price_period AS ENUM ('one_time', 'per_month', 'per_night');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================================
-- SHARED TRIGGER FUNCTION (needed by tables that use it)
-- ============================================================================

CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
	NEW.updated_at = NOW();
	RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- AGENTS TABLE  (normalized listing-agent / agency profiles)
-- ============================================================================

CREATE TABLE IF NOT EXISTS agents (
	id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
	first_name  TEXT NOT NULL,
	last_name   TEXT,
	email       TEXT,
	phone       TEXT,
	agency_name TEXT,
	bio         TEXT,
	is_verified BOOLEAN NOT NULL DEFAULT FALSE,
	avatar_url  TEXT,
	created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
	updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agents_phone ON agents(phone);
CREATE INDEX IF NOT EXISTS idx_agents_email ON agents(email);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_phone ON agents(phone) WHERE phone IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_email ON agents(email) WHERE email IS NOT NULL;

DROP TRIGGER IF EXISTS trg_agents_updated_at ON agents;
CREATE TRIGGER trg_agents_updated_at
	BEFORE UPDATE ON agents
	FOR EACH ROW
	EXECUTE FUNCTION update_modified_column();

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
	property_subtype TEXT,                       -- e.g. 'duplex', 'bungalow', 'maisonette'
	listing_type    listing_type NOT NULL,       -- sale (For Buy) | rent (For Rent / To Let)
	price_period    price_period NOT NULL DEFAULT 'one_time',
	status          property_status NOT NULL DEFAULT 'available',

	-- Pricing (KES by default; rentals are per-month, short-stays per-night)
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
	plot_dimensions TEXT,                          -- preserve raw, e.g. '50 x 100' / '80*40'
	land_size_raw   TEXT,                          -- preserve raw, e.g. '1/4 acre'
	year_built      INTEGER CHECK (year_built >= 1900 AND year_built <= 2100),
	floor_number    INTEGER,
	total_floors    INTEGER,

	-- Location (neighborhood -> road -> town -> city -> county -> country)
	location        TEXT NOT NULL,                -- neighborhood / area (e.g. "Kilimani")
	address         TEXT,                         -- road / street address
	town            TEXT,                         -- town / municipality
	city            TEXT NOT NULL DEFAULT 'Nairobi',
	county          TEXT,
	country         TEXT NOT NULL DEFAULT 'Kenya',
	latitude        NUMERIC,
	longitude       NUMERIC,

	-- Features (amenity feature tags — the old boolean feature flags are folded
	-- into `amenities` so there is a single source of truth, matching how
	-- Property254 renders "Property Features" on listing pages).
	amenities       TEXT[] DEFAULT '{}',          -- e.g. {swimming_pool,gym,parking,garden,security}
	furnished       BOOLEAN DEFAULT FALSE,        -- kept: distinct descriptor ("furnished apartments")

	-- Agent (FK to the normalized agents table)
	agent_id        UUID REFERENCES agents(id) ON DELETE SET NULL,

	-- Metadata
	source          TEXT,                         -- where the listing came from
	external_id     TEXT,                         -- ID from external MLS/CRM
	video_url       TEXT,                         -- optional property video / virtual tour link
	created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
	updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- New columns on a pre-existing properties table (no-op on a fresh DB where the
-- CREATE TABLE IF NOT EXISTS above already defined them).
ALTER TABLE properties ADD COLUMN IF NOT EXISTS property_subtype TEXT;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS price_period price_period NOT NULL DEFAULT 'one_time';
ALTER TABLE properties ADD COLUMN IF NOT EXISTS address TEXT;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS town TEXT;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS country TEXT NOT NULL DEFAULT 'Kenya';
ALTER TABLE properties ADD COLUMN IF NOT EXISTS plot_dimensions TEXT;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS land_size_raw TEXT;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS agent_id UUID REFERENCES agents(id) ON DELETE SET NULL;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS video_url TEXT;

-- Migration: backfill `agents` from any pre-existing denormalized agent columns,
-- link them via agent_id, then drop the obsolete columns. Guarded so it is a
-- no-op on a fresh database (where the old columns never existed).
DO $$
BEGIN
	IF EXISTS (SELECT 1 FROM information_schema.columns
			   WHERE table_name = 'properties' AND column_name = 'agent_name') THEN
		-- 1. Seed distinct agents from existing listings.
		INSERT INTO agents (first_name, last_name, phone, email, agency_name)
		SELECT
			CASE WHEN strpos(agent_name, ' ') > 0
				 THEN left(agent_name, strpos(agent_name, ' ') - 1)
				 ELSE agent_name END                        AS first_name,
			CASE WHEN strpos(agent_name, ' ') > 0
				 THEN trim(substr(agent_name, strpos(agent_name, ' ') + 1))
				 ELSE NULL END                              AS last_name,
			REPLACE(REPLACE(agent_phone, '+', ''), ' ', '') AS phone,
			agent_email,
			NULL
		FROM (SELECT DISTINCT agent_name, agent_phone, agent_email
			  FROM properties
			  WHERE agent_name IS NOT NULL OR agent_phone IS NOT NULL OR agent_email IS NOT NULL) s
		ON CONFLICT DO NOTHING;

		-- 2. Link properties to their agent.
		UPDATE properties p
		SET agent_id = a.id
		FROM agents a
		WHERE p.agent_id IS NULL
		  AND (p.agent_name IS NOT NULL OR p.agent_email IS NOT NULL)
		  AND ((a.phone = REPLACE(REPLACE(p.agent_phone, '+', ''), ' ', '') AND a.phone IS NOT NULL)
			   OR (a.email = p.agent_email AND a.email IS NOT NULL));
	END IF;
END $$;

-- ============================================================================
-- PROPERTY_IMAGES TABLE  (ordered gallery + featured image)
-- Created after `properties` so the foreign key resolves on a fresh database.
-- ============================================================================

CREATE TABLE IF NOT EXISTS property_images (
	id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
	property_id     UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
	url             TEXT NOT NULL,
	sort_order      INTEGER NOT NULL DEFAULT 0,
	is_featured     BOOLEAN NOT NULL DEFAULT FALSE,
	created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prop_images_property ON property_images(property_id, sort_order);
CREATE UNIQUE INDEX IF NOT EXISTS uq_property_images_property_sort ON property_images(property_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_prop_images_featured ON property_images(property_id) WHERE is_featured;

-- Migration: expand the old `images` TEXT[] column into the ordered
-- property_images table (first image = featured). Guarded / idempotent.
DO $$
BEGIN
	IF EXISTS (SELECT 1 FROM information_schema.columns
			   WHERE table_name = 'properties' AND column_name = 'images') THEN
		INSERT INTO property_images (property_id, url, sort_order, is_featured)
		SELECT p.id,
		       u.url,
		       u.ord - 1,
		       (u.ord = 1)
		FROM properties p
		,  LATERAL unnest(p.images) WITH ORDINALITY AS u(url, ord)
		WHERE p.images IS NOT NULL AND p.images <> '{}'
		ON CONFLICT (property_id, sort_order) DO NOTHING;
	END IF;
END $$;

-- Drop obsolete property columns (now redundant with agents / property_images / amenities).
ALTER TABLE properties DROP COLUMN IF EXISTS agent_name;
ALTER TABLE properties DROP COLUMN IF EXISTS agent_phone;
ALTER TABLE properties DROP COLUMN IF EXISTS agent_email;
ALTER TABLE properties DROP COLUMN IF EXISTS images;
ALTER TABLE properties DROP COLUMN IF EXISTS virtual_tour_url;
ALTER TABLE properties DROP COLUMN IF EXISTS has_garden;
ALTER TABLE properties DROP COLUMN IF EXISTS has_swimming_pool;
ALTER TABLE properties DROP COLUMN IF EXISTS pet_friendly;
ALTER TABLE properties DROP COLUMN IF EXISTS gated_community;
ALTER TABLE properties DROP COLUMN IF EXISTS parking_spots;

-- ============================================================================
-- INDEXES — PROPERTIES
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_properties_type      ON properties (property_type);
CREATE INDEX IF NOT EXISTS idx_properties_subtype   ON properties (property_subtype);
CREATE INDEX IF NOT EXISTS idx_properties_listing   ON properties (listing_type);
CREATE INDEX IF NOT EXISTS idx_properties_price_period ON properties (price_period);
CREATE INDEX IF NOT EXISTS idx_properties_status    ON properties (status);
CREATE INDEX IF NOT EXISTS idx_properties_price     ON properties (price);
CREATE INDEX IF NOT EXISTS idx_properties_bedrooms  ON properties (bedrooms);
CREATE INDEX IF NOT EXISTS idx_properties_bathrooms ON properties (bathrooms);
CREATE INDEX IF NOT EXISTS idx_properties_sqm       ON properties (square_meters);
CREATE INDEX IF NOT EXISTS idx_properties_lot       ON properties (lot_size_sqm);
CREATE INDEX IF NOT EXISTS idx_properties_location  ON properties (location);
CREATE INDEX IF NOT EXISTS idx_properties_town      ON properties (town);
CREATE INDEX IF NOT EXISTS idx_properties_city      ON properties (city);
CREATE INDEX IF NOT EXISTS idx_properties_country   ON properties (country);
CREATE INDEX IF NOT EXISTS idx_properties_agent     ON properties (agent_id);

-- Composite indexes for common Property254 query patterns
CREATE INDEX IF NOT EXISTS idx_properties_listing_price
	ON properties (listing_type, price);
CREATE INDEX IF NOT EXISTS idx_properties_type_listing_price
	ON properties (property_type, listing_type, price);
CREATE INDEX IF NOT EXISTS idx_properties_city_location
	ON properties (city, location);
CREATE INDEX IF NOT EXISTS idx_properties_beds_price
	ON properties (bedrooms, price);

-- GIN index for amenity feature tags
CREATE INDEX IF NOT EXISTS idx_properties_amenities
	ON properties USING GIN (amenities);

-- Partial index for active listings (most queries filter on this)
CREATE INDEX IF NOT EXISTS idx_properties_active
	ON properties (price, bedrooms, city)
	WHERE status = 'available';

-- Unique constraint on the seed fingerprint so re-runs update-in-place
CREATE UNIQUE INDEX IF NOT EXISTS uq_properties_fingerprint
	ON properties (title, location, price, listing_type, property_type, price_period);

DROP TRIGGER IF EXISTS trg_properties_updated_at ON properties;
CREATE TRIGGER trg_properties_updated_at
	BEFORE UPDATE ON properties
	FOR EACH ROW
	EXECUTE FUNCTION update_modified_column();

-- ============================================================================
-- CUSTOMER PROFILES  (unchanged)
-- ============================================================================

CREATE TABLE IF NOT EXISTS customer_profiles (
	whatsapp_id     TEXT PRIMARY KEY,
	preferred_name  TEXT,
	budget_range    TEXT,
	preferred_area  TEXT,
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
-- MPESA TRANSACTIONS  (unchanged)
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

-- ============================================================================
-- SCHEDULED VIEWINGS TABLE  (unchanged — references properties)
-- ============================================================================

CREATE TABLE IF NOT EXISTS scheduled_viewings (
	id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
	property_id         UUID REFERENCES properties(id) ON DELETE CASCADE,
	customer_phone      TEXT NOT NULL,
	customer_name       TEXT,
	viewing_date        TIMESTAMPTZ NOT NULL,
	duration_minutes    INTEGER NOT NULL DEFAULT 30,
	status              TEXT NOT NULL DEFAULT 'confirmed'
						CHECK (status IN ('confirmed', 'rescheduled', 'cancelled', 'completed')),
	notes               TEXT,
	created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
	updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_viewings_phone ON scheduled_viewings (customer_phone);
CREATE INDEX IF NOT EXISTS idx_viewings_property ON scheduled_viewings (property_id);
CREATE INDEX IF NOT EXISTS idx_viewings_date ON scheduled_viewings (viewing_date);

DROP TRIGGER IF EXISTS trg_scheduled_viewings_modified_at ON scheduled_viewings;
CREATE TRIGGER trg_scheduled_viewings_modified_at
	BEFORE UPDATE ON scheduled_viewings
	FOR EACH ROW
	EXECUTE FUNCTION update_modified_column();

-- ============================================================================
-- PROPERTY INQUIRIES (LEADS)  — enriched with name / email / agent
-- ============================================================================

CREATE TABLE IF NOT EXISTS property_inquiries (
	id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
	customer_phone      TEXT NOT NULL,
	customer_name       TEXT,
	customer_email      TEXT,
	property_id         UUID REFERENCES properties(id) ON DELETE SET NULL,
	agent_id            UUID REFERENCES agents(id) ON DELETE SET NULL,
	inquiry_type        TEXT NOT NULL DEFAULT 'general',
	message             TEXT,
	metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
	created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inquiries_phone ON property_inquiries (customer_phone);
CREATE INDEX IF NOT EXISTS idx_inquiries_property ON property_inquiries (property_id);
CREATE INDEX IF NOT EXISTS idx_inquiries_agent ON property_inquiries (agent_id);

-- Migration safety for pre-existing property_inquiries (older shape lacked these).
ALTER TABLE property_inquiries ADD COLUMN IF NOT EXISTS customer_name TEXT;
ALTER TABLE property_inquiries ADD COLUMN IF NOT EXISTS customer_email TEXT;
ALTER TABLE property_inquiries ADD COLUMN IF NOT EXISTS agent_id UUID REFERENCES agents(id) ON DELETE SET NULL;

-- ============================================================================
-- CONVERSATION SUMMARIES  (unchanged)
-- ============================================================================

CREATE TABLE IF NOT EXISTS conversation_summaries (
	whatsapp_id     TEXT PRIMARY KEY,
	summary         TEXT NOT NULL,
	metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
	created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
	updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversation_summaries_phone ON conversation_summaries (whatsapp_id);

DROP TRIGGER IF EXISTS trg_conversation_summaries_modified_at ON conversation_summaries;
CREATE TRIGGER trg_conversation_summaries_modified_at
	BEFORE UPDATE ON conversation_summaries
	FOR EACH ROW
	EXECUTE FUNCTION update_modified_column();

-- ============================================================================
-- CONVERSATION MESSAGES  (unchanged)
-- ============================================================================

CREATE TABLE IF NOT EXISTS conversation_messages (
	id              BIGSERIAL PRIMARY KEY,
	whatsapp_id     TEXT NOT NULL,
	role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
	content         JSONB NOT NULL,
	wamid           TEXT UNIQUE,
	source          TEXT NOT NULL DEFAULT 'whatsapp',
	metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
	created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conv_msg_whatsapp_created
	ON conversation_messages (whatsapp_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_conv_msg_created
	ON conversation_messages (created_at);

-- ============================================================================
-- BOT SETTINGS / OWNER CONFIG  (unchanged)
-- ============================================================================

CREATE TABLE IF NOT EXISTS bot_settings (
	key             TEXT PRIMARY KEY,
	value           TEXT NOT NULL,
	metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
	created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
	updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_bot_settings_modified_at ON bot_settings;
CREATE TRIGGER trg_bot_settings_modified_at
	BEFORE UPDATE ON bot_settings
	FOR EACH ROW
	EXECUTE FUNCTION update_modified_column();
