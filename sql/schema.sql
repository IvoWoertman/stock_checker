-- Freezer Tracker lakehouse schema.
--
-- Run this once in the Databricks SQL editor to bootstrap the schema.
-- It creates Unity Catalog managed Delta tables with catalog commits enabled,
-- which allows the app's multi-table transactions (see PLAN.md section 6).
--
-- If you use a catalog or schema other than main.freezer, change the names
-- below AND set DATABRICKS_CATALOG / DATABRICKS_SCHEMA for the app.

CREATE CATALOG IF NOT EXISTS main;
CREATE SCHEMA IF NOT EXISTS main.freezer;

-- Products: what a package contains. A retail barcode (gtin) identifies a
-- product, not a particular package.
CREATE TABLE IF NOT EXISTS main.freezer.products (
  product_id           STRING       NOT NULL,
  name                 STRING       NOT NULL,
  brand                STRING,
  gtin                 STRING,
  preferred_unit       STRING       NOT NULL,
  usual_package_size_g DECIMAL(10,2),
  created_at           TIMESTAMP    NOT NULL,
  updated_at           TIMESTAMP    NOT NULL
) TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported');

-- Lots: one physical package in the freezer. lot_id is also the unique QR
-- payload printed on the label.
CREATE TABLE IF NOT EXISTS main.freezer.lots (
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
CREATE TABLE IF NOT EXISTS main.freezer.inventory_events (
  event_id         STRING        NOT NULL,
  op_id            STRING        NOT NULL,
  lot_id           STRING        NOT NULL,
  event_type       STRING        NOT NULL,
  quantity_delta_g DECIMAL(10,2) NOT NULL,
  event_time       TIMESTAMP     NOT NULL,
  actor            STRING,
  method           STRING        NOT NULL,
  note             STRING,
  reversed_event_id STRING
) TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported');

ALTER TABLE main.freezer.inventory_events
  ADD CONSTRAINT event_type_check CHECK (
    event_type IN ('STOCK_IN', 'USE', 'ADJUST', 'DISCARD', 'REVERSAL')
  );

ALTER TABLE main.freezer.inventory_events
  ADD CONSTRAINT method_check CHECK (
    method IN ('ESTIMATE', 'WEIGHED', 'CORRECTION', 'SYSTEM')
  );

-- Current stock per lot, derived from the ledger.
CREATE OR REPLACE VIEW main.freezer.v_current_lot_stock AS
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
FROM main.freezer.lots l
JOIN main.freezer.products p ON p.product_id = l.product_id
LEFT JOIN main.freezer.inventory_events e ON e.lot_id = l.lot_id
GROUP BY
  l.lot_id, l.product_id, p.name, p.brand, p.gtin,
  l.added_date, l.best_before_date, l.location, l.notes;
