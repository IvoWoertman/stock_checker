-- Apply to an existing main.stock schema created before the
-- category/matching/aggregation changes. Adds the new product columns and the
-- active-stock / product-stock views. Safe to run more than once.

ALTER TABLE main.stock.products ADD COLUMNS (
  name_key STRING,
  category STRING,
  default_best_before_days INT
);

CREATE OR REPLACE VIEW main.stock.v_active_lot_stock AS
SELECT * FROM main.stock.v_current_lot_stock WHERE grams_remaining > 0;

CREATE OR REPLACE VIEW main.stock.v_product_stock AS
SELECT
  p.product_id,
  p.name,
  p.brand,
  p.category,
  COUNT(b.lot_id)                             AS lot_count,
  COALESCE(SUM(b.grams_remaining), 0)         AS total_grams,
  MIN(l.added_date)                           AS oldest_added_date
FROM main.stock.products p
JOIN main.stock.lots l ON l.product_id = p.product_id
JOIN (
  SELECT lot_id, SUM(quantity_delta_g) AS grams_remaining
  FROM main.stock.inventory_events
  GROUP BY lot_id
  HAVING SUM(quantity_delta_g) > 0
) b ON b.lot_id = l.lot_id
GROUP BY p.product_id, p.name, p.brand, p.category;
