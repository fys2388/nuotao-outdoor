-- =============================================================================
-- Seed: enable the 8 current B2C (WooCommerce) products on the public B2B
-- no-price showcase.
--
-- SAFETY / SCOPE
--   * PREPARED ONLY — DO **NOT** EXECUTE against production in this round.
--     Owner runs this manually AFTER backing up, or it is applied through the
--     normal reviewed release process.
--   * Idempotent: re-running is safe (UPDATE ... WHERE already-filters).
--   * Only flips b2b_showcase_enabled -> true. It NEVER touches price/cost/
--     stock/SKU/vendor fields. The public b2b-showcase API is field-allowlisted
--     and structurally cannot emit price, so enabling a product can never leak
--     B2C pricing.
--   * b2b_public_slug is left NULL on purpose: the service derives the public
--     slug from the product name when b2b_public_slug is NULL
--     (see b2b_showcase_service._public_slug), so no slug backfill is required.
--
-- MATCHING
--   Products are matched by name keyword (ILIKE). The 8 products are the
--   currently-listed DTC/WooCommerce items. Keyword match is used because the
--   exact stored `name` may include extra suffixes from the Woo sync. Review
--   the matched row count before committing (see verification query at bottom).
-- =============================================================================

-- Enable showcase for the 8 products (keyword match on name).
UPDATE products
SET b2b_showcase_enabled = true
WHERE deleted_at IS NULL
  AND (
        name ILIKE '%headlamp%'      OR name ILIKE '%headlamp%'      -- MH1 rechargeable headlamp
     OR name ILIKE '%titanium%'      OR name ILIKE '%water bottle%'  -- pure-titanium sports bottle
     OR name ILIKE '%gaiter%'                                        -- Snow Gaiters
     OR name ILIKE '%600d%'          OR name ILIKE '%storage bag%'   -- 600D storage bag / organiser
     OR name ILIKE '%crampon%'       OR name ILIKE '%ice crampon%'   -- Ice Crampons
     OR name ILIKE '%sleeping bag liner%' OR name ILIKE '%heated liner%' -- heated sleeping-bag liner
     OR name ILIKE '%inflatable%'    OR name ILIKE '%sleeping pad%'  -- foot-press inflatable pad
     OR name ILIKE '%water filter%'  OR name ILIKE '%filtration%'    -- portable water filter
  );

-- -----------------------------------------------------------------------------
-- VERIFICATION (run BEFORE committing / in a transaction):
-- Confirm exactly the intended 8 products were matched and enabled.
-- -----------------------------------------------------------------------------
-- SELECT name, sku, category, b2b_showcase_enabled
-- FROM products
-- WHERE deleted_at IS NULL AND b2b_showcase_enabled = true
-- ORDER BY name;
--
-- Expected: the 8 DTC products (headlamp, titanium bottle, gaiters, 600D bag,
-- crampons, heated liner, inflatable pad, water filter). If more/fewer rows
-- appear, tighten the keyword filters above before committing.
--
-- ROLLBACK (if needed):
--   UPDATE products SET b2b_showcase_enabled = false WHERE <same name filters>;
-- =============================================================================