-- Stock Tracker lakehouse schema.
--
-- Run this once in the Databricks SQL editor to bootstrap the schema, or run
-- sql/migrate.sql against an existing schema created before the
-- category/matching/aggregation changes.
--
-- Tables are Unity Catalog managed Delta tables with catalog commits enabled,
-- which allows the app's multi-table transactions.
--
-- If you use a catalog or schema other than main.stock, change the names below
-- AND set DATABRICKS_CATALOG / DATABRICKS_SCHEMA for the app.

CREATE CATALOG IF NOT EXISTS main;
CREATE SCHEMA IF NOT EXISTS main.stock;

-- Products: what a package contains. A retail barcode (gtin) identifies a
-- product, not a particular package. name_key is the canonical form used to
-- match "ground beef" with "beef"; category is auto-assigned from keywords.
CREATE TABLE IF NOT EXISTS main.stock.products (
  product_id             STRING       NOT NULL,
  name                   STRING       NOT NULL,
  brand                  STRING,
  gtin                   STRING,
  preferred_unit         STRING       NOT NULL,
  usual_package_size_g   DECIMAL(10,2),
  name_key               STRING,
  category               STRING,
  default_best_before_days INT,
  created_at             TIMESTAMP    NOT NULL,
  updated_at             TIMESTAMP    NOT NULL
) TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported');

-- Lots: one physical package. lot_id is also the unique QR payload printed on
-- the label.
CREATE TABLE IF NOT EXISTS main.stock.lots (
  lot_id           STRING    NOT NULL,
  product_id       STRING    NOT NULL,
  added_date       DATE      NOT NULL,
  best_before_date DATE,
  location         STRING,
  notes            STRING,
  created_at       TIMESTAMP NOT NULL
) TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported');

-- Inventory events: the append-only ledger. Current stock is derived by
-- summing quantity_delta_g per lot; negative stock is a data-quality error.
CREATE TABLE IF NOT EXISTS main.stock.inventory_events (
  event_id          STRING        NOT NULL,
  op_id             STRING        NOT NULL,
  lot_id            STRING        NOT NULL,
  event_type        STRING        NOT NULL,
  quantity_delta_g  DECIMAL(10,2) NOT NULL,
  event_time        TIMESTAMP     NOT NULL,
  actor             STRING,
  method            STRING        NOT NULL,
  note              STRING,
  reversed_event_id STRING
) TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported');

ALTER TABLE main.stock.inventory_events
  ADD CONSTRAINT event_type_check CHECK (
    event_type IN ('STOCK_IN', 'USE', 'ADJUST', 'DISCARD', 'REVERSAL')
  );

ALTER TABLE main.stock.inventory_events
  ADD CONSTRAINT method_check CHECK (
    method IN ('ESTIMATE', 'WEIGHED', 'CORRECTION', 'SYSTEM')
  );

-- Current stock per lot, derived from the ledger (all lots, including empty).
CREATE OR REPLACE VIEW main.stock.v_current_lot_stock AS
SELECT
  l.lot_id,
  l.product_id,
  p.name                 AS product_name,
  p.brand                AS brand,
  p.gtin                 AS gtin,
  l.added_date           AS added_date,
  l.best_before_date     AS best_before_date,
  l.location             AS location,
  l.notes                AS notes,
  COALESCE(SUM(e.quantity_delta_g), 0) AS grams_remaining,
  MIN(e.event_time)      AS first_event_time,
  MAX(e.event_time)      AS last_event_time
FROM main.stock.lots l
JOIN main.stock.products p ON p.product_id = l.product_id
LEFT JOIN main.stock.inventory_events e ON e.lot_id = l.lot_id
GROUP BY
  l.lot_id, l.product_id, p.name, p.brand, p.gtin,
  l.added_date, l.best_before_date, l.location, l.notes;

-- Active lots only (grams remaining > 0). Lots that are used up or discarded
-- drop out of the active overview.
CREATE OR REPLACE VIEW main.stock.v_active_lot_stock AS
SELECT * FROM main.stock.v_current_lot_stock WHERE grams_remaining > 0;

-- Product-level overview: number of active packages and total grams per product.
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
