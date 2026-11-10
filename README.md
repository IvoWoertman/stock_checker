# Freezer Tracker

A phone-first freezer inventory app for two people, running on Databricks with Unity Catalog managed Delta tables (the lakehouse).

See [PLAN.md](PLAN.md) for the product scope, architecture, ACID transaction design, Free Edition constraints, milestones, and acceptance criteria.

## Status

First slice built: lakehouse schema, a Flask app with atomic inventory writes, and a phone-first UI. The next step is the Databricks feasibility spike (milestone 1) to validate the app-to-SQL-warehouse connection and the multi-table transaction on your actual workspace.

## Layout

```
app.yaml            Databricks App runtime config (gunicorn + port)
requirements.txt    Python dependencies
app.py              Flask app and JSON API routes
db.py               Databricks SQL connection + query helpers
service.py          Business logic and atomic writes
sql/schema.sql      Lakehouse DDL (managed Delta tables + stock view)
sql/seed.sql        Sample data for testing
static/             Phone-first HTML/JS/CSS frontend
.env.example        Local-dev environment variables (not committed)
```

## Data model

- `products` — what a package contains (name, optional GTIN/EAN).
- `lots` — one physical package; `lot_id` doubles as the QR label payload.
- `inventory_events` — append-only ledger; current stock is the sum of `quantity_delta_g` per lot.
- `v_current_lot_stock` — view that derives grams remaining per lot.

All tables are Unity Catalog **managed Delta** tables with **catalog commits** enabled so the app's writes can span multiple tables atomically.

## Deploy to Databricks

1. In your workspace, run `sql/schema.sql` (once) in the SQL editor to create the tables and view. Optionally run `sql/seed.sql` to add sample data.
2. Create a Databricks App from this repository (or workspace folder).
3. Attach a **SQL warehouse** as an app resource. Databricks injects the connection details and grants the app's service principal.
4. Grant the app's service principal `SELECT` and `MODIFY` on `main.freezer` and `CAN USE` on the warehouse.
5. Deploy. The app runs `gunicorn` per `app.yaml`.

## Run locally

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in hostname, http_path, token
export $(grep -v '^#' .env | xargs)
python app.py          # http://localhost:8080
```

Local development uses a personal access token (`DATABRICKS_TOKEN`). Inside the Databricks App runtime, Databricks provides the service-principal OAuth credentials automatically.

## Security notes

No credentials or household data belong in this repository. `.env` is git-ignored. The app never exposes Databricks credentials to the browser; the browser talks only to the Flask JSON API.
