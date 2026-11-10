"""Connection and query helpers for the Databricks lakehouse.

Inside a Databricks App, Databricks provisions a service principal and injects
these environment variables: DATABRICKS_HOST (workspace URL), DATABRICKS_CLIENT_ID
and DATABRICKS_CLIENT_SECRET (service-principal OAuth). A SQL warehouse attached
as an app resource is exposed by ID (see app.yaml `valueFrom: sql-warehouse`).
For local development, set DATABRICKS_TOKEN (a personal access token) plus
DATABRICKS_SERVER_HOSTNAME and DATABRICKS_HTTP_PATH. See .env.example.
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


def _service_principal_provider(host: str):
    from databricks.sdk.core import Config, oauth_service_principal

    config = Config(
        host=host,
        client_id=os.environ["DATABRICKS_CLIENT_ID"],
        client_secret=os.environ["DATABRICKS_CLIENT_SECRET"],
    )
    return oauth_service_principal(config)


def _server_hostname():
    """Workspace hostname without the URL scheme.

    In the app runtime this comes from DATABRICKS_HOST (a full URL). Locally,
    DATABRICKS_SERVER_HOSTNAME is set directly.
    """
    host = os.environ.get("DATABRICKS_HOST") or os.environ.get("DATABRICKS_SERVER_HOSTNAME")
    if host:
        return host.split("://", 1)[-1].rstrip("/")
    raise KeyError("DATABRICKS_HOST (app runtime) or DATABRICKS_SERVER_HOSTNAME (local) is required.")


def _http_path():
    """Resolve the warehouse HTTP path.

    The warehouse is referenced by ID (see app.yaml `valueFrom: sql-warehouse`),
    so the HTTP path is built from that ID unless DATABRICKS_HTTP_PATH is set
    directly (for local development).
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

    App runtime: service-principal OAuth (DATABRICKS_CLIENT_ID / SECRET) against
    DATABRICKS_HOST. Local development: personal access token (DATABRICKS_TOKEN).
    """
    client_id = os.environ.get("DATABRICKS_CLIENT_ID")
    client_secret = os.environ.get("DATABRICKS_CLIENT_SECRET")

    if client_id and client_secret:
        host = os.environ.get("DATABRICKS_HOST")
        if not host:
            raise KeyError("DATABRICKS_HOST is not set in the app runtime.")
        kwargs = {
            "server_hostname": _server_hostname(),
            "http_path": _http_path(),
            "credentials_provider": lambda: _service_principal_provider(host),
            "user_agent_entry": "stock-tracker",
        }
    else:
        kwargs = {
            "server_hostname": _server_hostname(),
            "http_path": _http_path(),
            "access_token": os.environ["DATABRICKS_TOKEN"],
            "user_agent_entry": "stock-tracker",
        }

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
