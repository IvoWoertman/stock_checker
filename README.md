# Stock Tracker

A phone-first stock inventory app for two people, running on Databricks. The
app reads and writes a **Lakebase** (managed Postgres) database for fast,
low-latency interactions; the data can be registered in Unity Catalog later for
analytics.

See [PLAN.md](PLAN.md) for the product scope, features, and milestones.

## Layout

```
app.yaml              Databricks App runtime config (gunicorn + port)
requirements.txt      Python dependencies
requirements-dev.txt  Test/lint dependencies (CI only)
app.py                Flask app and JSON API routes
db.py                 Lakebase (Postgres) connection + schema bootstrap
service.py            Business logic and atomic writes
catalog.py            Name normalization + auto-categorization
static/               Phone-first HTML/JS/CSS frontend (incl. barcode scanner)
tests/                Unit and integration tests
.github/workflows     CI (lint + test on push/PR)
.env.example          Local-dev environment variables (not committed)
```

## Data model (Postgres, schema `stock`)

- `products` — what a package contains (name, optional GTIN/EAN, `name_key` for
  matching "ground beef" with "beef", auto-assigned `category`, optional
  `default_best_before_days`).
- `lots` — one physical package; `lot_id` doubles as the QR label payload.
- `inventory_events` — append-only ledger; current stock is the sum of
  `quantity_delta_g` per lot. `DISCARD` tracks waste separately from use.
- `v_current_lot_stock`, `v_active_lot_stock`, `v_product_stock` — SQL views.

Unlike the earlier Delta version, these are real Postgres tables with enforced
primary/foreign keys and CHECK constraints. The schema is created automatically
by the app on first page load (`db.bootstrap()`, idempotent).

## Deploy to Databricks

1. Provision a **Lakebase** project (managed Postgres). It comes with a
   `production` branch and a `databricks_postgres` database.
2. Create a Databricks App from this repository.
3. Add a **Database** resource: pick the Lakebase project, branch, and database;
   permission **Can connect and create**; keep the default key `postgres`.
   Databricks creates a Postgres role for the app's service principal and
   injects the `PG*` connection variables automatically.
4. Deploy. On first load the app creates its `stock` schema and tables.

See [docs/DEPLOY.md](docs/DEPLOY.md) for the full checklist.

## Run locally

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://user:pass@host:5432/dbname   # or set PG* vars
python app.py          # http://localhost:8080
```

Local development uses `DATABASE_URL`; in the Databricks App runtime, the
`PG*` environment variables are injected automatically.

## Analytics (later)

Register the Lakebase database in Unity Catalog to query it with Databricks SQL
alongside the lakehouse, or stream its changes into Delta via change-data-capture.

## Security notes

No credentials or household data belong in this repository. `.env` is
git-ignored. The app never exposes database credentials to the browser; the
browser talks only to the Flask JSON API.
