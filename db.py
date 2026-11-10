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
SCHEMA = os.environ.get("DATABRICKS_SCHEMA", "freezer")


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
        "http_path": os.environ["DATABRICKS_HTTP_PATH"],
        "user_agent_entry": "freezer-tracker",
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
