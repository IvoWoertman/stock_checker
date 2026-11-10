-- Sample data (run once, for testing the UI against a fresh schema).

INSERT INTO main.stock.products
  (product_id, name, brand, gtin, preferred_unit, usual_package_size_g, name_key, category, default_best_before_days, created_at, updated_at)
VALUES
  ('00000000-0000-0000-0000-000000000001', 'Ground beef', NULL, '8712345678901', 'g', 500, 'beef', 'Meat', 90, current_timestamp(), current_timestamp()),
  ('00000000-0000-0000-0000-000000000002', 'Green peas', 'Frozen Co', NULL, 'g', 1000, 'green peas', 'Vegetables', NULL, current_timestamp(), current_timestamp());

INSERT INTO main.stock.lots
  (lot_id, product_id, added_date, best_before_date, location, notes, created_at)
VALUES
  ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', current_date(), DATEADD(day, 90, current_date()), 'Drawer 1', 'mince for lasagna', current_timestamp()),
  ('10000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', current_date(), DATEADD(day, 90, current_date()), 'Drawer 1', 'burgers', current_timestamp()),
  ('10000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000002', current_date(), NULL, 'Drawer 2', NULL, current_timestamp());

INSERT INTO main.stock.inventory_events
  (event_id, op_id, lot_id, event_type, quantity_delta_g, event_time, actor, method, note, reversed_event_id)
VALUES
  ('20000000-0000-0000-0000-000000000001', 'seed-1', '10000000-0000-0000-0000-000000000001', 'STOCK_IN', 500, current_timestamp(), 'seed', 'SYSTEM', NULL, NULL),
  ('20000000-0000-0000-0000-000000000002', 'seed-2', '10000000-0000-0000-0000-000000000002', 'STOCK_IN', 400, current_timestamp(), 'seed', 'SYSTEM', NULL, NULL),
  ('20000000-0000-0000-0000-000000000003', 'seed-3', '10000000-0000-0000-0000-000000000003', 'STOCK_IN', 1000, current_timestamp(), 'seed', 'SYSTEM', NULL, NULL);
