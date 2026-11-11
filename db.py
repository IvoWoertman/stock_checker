"""Connection and query helpers for the Lakebase (Postgres) database.

Inside a Databricks App, attaching a Lakebase database as an app resource makes
Databricks inject the standard libpq environment variables (PGHOST, PGPORT,
PGDATABASE, PGUSER, PGPASSWORD). ``psycopg2.connect()`` reads those
automatically, so no credentials live in code. For local development, set
``DATABASE_URL`` instead.
"""
import os
import time
from contextlib import closing
from datetime import date as _date
from datetime import datetime as _datetime
from datetime import time as _time
from decimal import Decimal

import psycopg2
from databricks.sdk import WorkspaceClient

SCHEMA = os.environ.get("PG_SCHEMA", "stock")

# Schema DDL, run idempotently by bootstrap() on first page load.
_DDL = [
    f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}",
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.products (
      product_id             TEXT PRIMARY KEY,
      name                   TEXT NOT NULL,
      brand                  TEXT,
      gtin                   TEXT,
      preferred_unit         TEXT NOT NULL,
      usual_package_size_g   NUMERIC(10,2),
      name_key               TEXT,
      category               TEXT,
      default_best_before_days INTEGER,
      min_stock_g            NUMERIC(10,2),
      created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    f"ALTER TABLE {SCHEMA}.products ADD COLUMN IF NOT EXISTS min_stock_g NUMERIC(10,2)",
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.lots (
      lot_id           TEXT PRIMARY KEY,
      product_id       TEXT NOT NULL REFERENCES {SCHEMA}.products(product_id),
      added_date       DATE NOT NULL,
      best_before_date DATE,
      location         TEXT,
      notes            TEXT,
      created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.inventory_events (
      event_id          TEXT PRIMARY KEY,
      op_id             TEXT NOT NULL,
      lot_id            TEXT NOT NULL REFERENCES {SCHEMA}.lots(lot_id),
      event_type        TEXT NOT NULL,
      quantity_delta_g  NUMERIC(10,2) NOT NULL,
      event_time        TIMESTAMPTZ NOT NULL DEFAULT now(),
      actor             TEXT,
      method            TEXT NOT NULL,
      note              TEXT,
      reversed_event_id TEXT
    )
    """,
    f"ALTER TABLE {SCHEMA}.inventory_events DROP CONSTRAINT IF EXISTS event_type_check",
    f"ALTER TABLE {SCHEMA}.inventory_events ADD CONSTRAINT event_type_check CHECK (event_type IN ('STOCK_IN','USE','ADJUST','DISCARD','REVERSAL'))",
    f"ALTER TABLE {SCHEMA}.inventory_events DROP CONSTRAINT IF EXISTS method_check",
    f"ALTER TABLE {SCHEMA}.inventory_events ADD CONSTRAINT method_check CHECK (method IN ('ESTIMATE','WEIGHED','CORRECTION','SYSTEM'))",
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.shopping_items (
      item_id    TEXT PRIMARY KEY,
      name       TEXT NOT NULL,
      note       TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      done_at    TIMESTAMPTZ
    )
    """,
    f"""
    CREATE OR REPLACE VIEW {SCHEMA}.v_current_lot_stock AS
    SELECT
      l.lot_id, l.product_id,
      p.name AS product_name, p.brand, p.gtin,
      l.added_date, l.best_before_date, l.location, l.notes,
      COALESCE(SUM(e.quantity_delta_g), 0) AS grams_remaining,
      MIN(e.event_time) AS first_event_time,
      MAX(e.event_time) AS last_event_time
    FROM {SCHEMA}.lots l
    JOIN {SCHEMA}.products p ON p.product_id = l.product_id
    LEFT JOIN {SCHEMA}.inventory_events e ON e.lot_id = l.lot_id
    GROUP BY l.lot_id, l.product_id, p.name, p.brand, p.gtin,
             l.added_date, l.best_before_date, l.location, l.notes
    """,
    f"CREATE OR REPLACE VIEW {SCHEMA}.v_active_lot_stock AS SELECT * FROM {SCHEMA}.v_current_lot_stock WHERE grams_remaining > 0",
    f"""
    CREATE OR REPLACE VIEW {SCHEMA}.v_product_stock AS
    SELECT
      p.product_id, p.name, p.brand, p.category, p.min_stock_g,
      COUNT(b.lot_id) AS lot_count,
      COALESCE(SUM(b.grams_remaining), 0) AS total_grams,
      MIN(l.added_date) AS oldest_added_date,
      (p.min_stock_g IS NOT NULL AND COALESCE(SUM(b.grams_remaining), 0) < p.min_stock_g) AS low_stock
    FROM {SCHEMA}.products p
    LEFT JOIN {SCHEMA}.lots l ON l.product_id = p.product_id
    LEFT JOIN (
      SELECT lot_id, SUM(quantity_delta_g) AS grams_remaining
      FROM {SCHEMA}.inventory_events
      GROUP BY lot_id
      HAVING SUM(quantity_delta_g) > 0
    ) b ON b.lot_id = l.lot_id
    GROUP BY p.product_id, p.name, p.brand, p.category, p.min_stock_g
    """,
]


def fq(table: str) -> str:
    """Schema-qualified table name."""
    return f"{SCHEMA}.{table}"


_workspace_client = None
_token_cache = {"token": None, "expires": 0.0}


def _get_workspace_client():
    global _workspace_client
    if _workspace_client is None:
        host = os.environ["DATABRICKS_HOST"]
        if not host.startswith(("http://", "https://")):
            host = "https://" + host
        _workspace_client = WorkspaceClient(
            host=host,
            client_id=os.environ["DATABRICKS_CLIENT_ID"],
            client_secret=os.environ["DATABRICKS_CLIENT_SECRET"],
        )
    return _workspace_client


def _database_password():
    """Mint a short-lived Lakebase database credential (OAuth token), cached."""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires"]:
        return _token_cache["token"]
    endpoint = os.environ["ENDPOINT_NAME"]
    credential = _get_workspace_client().postgres.generate_database_credential(endpoint=endpoint)
    _token_cache["token"] = credential.token
    _token_cache["expires"] = now + 50 * 60  # tokens live 60 min; refresh early
    return credential.token


def connect(autocommit: bool = True):
    """Open a Postgres connection.

    In the app runtime, psycopg2 reads PGHOST/PGPORT/PGDATABASE/PGUSER from the
    environment; the password is a Lakebase OAuth database credential minted via
    the Databricks SDK. Locally, DATABASE_URL takes precedence.
    """
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        conn = psycopg2.connect(dsn)
    else:
        if not os.environ.get("PGHOST"):
            raise RuntimeError(
                "No database connection configured: attach the Lakebase "
                "database resource to the app and redeploy (PGHOST is missing)."
            )
        conn = psycopg2.connect(
            host=os.environ["PGHOST"],
            port=os.environ.get("PGPORT", "5432"),
            dbname=os.environ["PGDATABASE"],
            user=os.environ["PGUSER"],
            password=_database_password(),
            sslmode=os.environ.get("PGSSLMODE", "require"),
        )
    conn.autocommit = autocommit
    return conn


def bootstrap():
    """Create the schema and tables if they don't exist yet (idempotent)."""
    with closing(connect()) as conn, conn.cursor() as cur:
        for statement in _DDL:
            cur.execute(statement)


def _jsonable(value):
    """Convert driver-native types (Decimal, date, datetime) to JSON-safe."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (_datetime, _date, _time)):
        return value.isoformat()
    return value


def rows(sql_text: str, params=None):
    """Run a SELECT and return a list of dicts with JSON-safe values."""
    with closing(connect()) as conn, conn.cursor() as cur:
        cur.execute(sql_text, params or [])
        cols = [c[0] for c in cur.description]
        return [{c: _jsonable(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def one(sql_text: str, params=None):
    result = rows(sql_text, params)
    return result[0] if result else None
