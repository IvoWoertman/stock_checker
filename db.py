"""Connection and query helpers for the Databricks lakehouse.

Inside a Databricks App, Databricks provisions a service principal and injects
the connection details (server hostname, HTTP path, OAuth client id/secret) as
environment variables when a SQL warehouse is attached as an app resource.
For local development, set DATABRICKS_TOKEN (a personal access token) plus the
hostname and HTTP path. See .env.example.
"""
import os
from datetime import date as _date
from datetime import datetime as _datetime
from datetime import time as _time
from decimal import Decimal

from databricks import sql

CATALOG = os.environ.get("DATABRICKS_CATALOG", "main")
SCHEMA = os.environ.get("DATABRICKS_SCHEMA", "stock")


def fq(table: str) -> str:
    """Fully-qualified table name in the app's catalog and schema."""
    return f"{CATALOG}.{SCHEMA}.{table}"


def _service_principal_provider():
    from databricks.sdk.core import Config, oauth_service_principal

    config = Config(
        host=f"https://{os.environ['DATABRICKS_SERVER_HOSTNAME']}",
        client_id=os.environ["DATABRICKS_CLIENT_ID"],
        client_secret=os.environ["DATABRICKS_CLIENT_SECRET"],
    )
    return oauth_service_principal(config)


def _http_path():
    """Resolve the warehouse HTTP path.

    Databricks injects DATABRICKS_SERVER_HOSTNAME and the service-principal
    OAuth credentials as default environment variables. The warehouse is
    referenced by ID (see app.yaml `valueFrom: sql-warehouse`), so the HTTP
    path is built from that ID unless DATABRICKS_HTTP_PATH is set directly
    (for local development or if Databricks provides it).
    """
    http_path = os.environ.get("DATABRICKS_HTTP_PATH")
    if http_path:
        return http_path
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if warehouse_id:
        return f"/sql/1.0/warehouses/{warehouse_id}"
    raise KeyError(
        "Set DATABRICKS_HTTP_PATH or DATABRICKS_WAREHOUSE_ID to connect to a SQL warehouse."
    )


def connect(autocommit: bool = True):
    """Open a connection to the SQL warehouse.

    Authentication order:
      1. OAuth machine-to-machine (app service principal) when
         DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET are set.
      2. Personal access token (local dev) when DATABRICKS_TOKEN is set.
      3. OAuth user-to-machine (interactive) otherwise.
    """
    kwargs = {
        "server_hostname": os.environ["DATABRICKS_SERVER_HOSTNAME"],
        "http_path": _http_path(),
        "user_agent_entry": "stock-tracker",
    }
    if os.environ.get("DATABRICKS_CLIENT_ID") and os.environ.get("DATABRICKS_CLIENT_SECRET"):
        kwargs["credentials_provider"] = _service_principal_provider
    elif os.environ.get("DATABRICKS_TOKEN"):
        kwargs["access_token"] = os.environ["DATABRICKS_TOKEN"]
    else:
        kwargs["auth_type"] = "databricks-oauth"
    if not autocommit:
        kwargs["autocommit"] = False
    return sql.connect(**kwargs)


def _jsonable(value):
    """Convert driver-native types (Decimal, date, datetime) to JSON-safe."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (_datetime, _date, _time)):
        return value.isoformat()
    return value


def rows(sql_text: str, params=None):
    """Run a SELECT and return a list of dicts with JSON-safe values."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text, params or [])
            cols = [c[0] for c in cur.description]
            return [{c: _jsonable(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def one(sql_text: str, params=None):
    result = rows(sql_text, params)
    return result[0] if result else None
