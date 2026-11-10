-- Reset the stock schema to an empty state (destroys all data).
-- Run this, then run schema.sql to recreate the tables and views.
DROP SCHEMA IF EXISTS main.stock CASCADE;
