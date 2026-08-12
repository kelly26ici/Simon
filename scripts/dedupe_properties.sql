-- Samantha Real Estate — Supabase dedupe migration
-- Keeps the newest property row per fingerprint: (title, location, price)
-- Safe to re-run.

WITH ranked AS (
  SELECT
    id,
    ROW_NUMBER() OVER (
      PARTITION BY title, location, price
      ORDER BY created_at DESC, updated_at DESC, id DESC
    ) AS rn
  FROM properties
)
DELETE FROM properties
WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
