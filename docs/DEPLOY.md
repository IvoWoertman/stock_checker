# Deploy the Stock Tracker to Databricks

Step-by-step checklist to get the app running against a Lakebase (Postgres)
database, validate it, and share it with the second household member.

## Prerequisites

- A Databricks workspace (Free Edition works for learning, with the 24-hour app
  stop and fair-use caveats noted in PLAN.md).
- Permission to create a **Lakebase** project and Databricks Apps.

## 1. Provision a Lakebase database

1. In the workspace, open **Lakebase** and create a project (a managed Postgres
   instance). Free Edition allows one project with scale-to-zero compute.
2. Note that the project comes with a `production` branch and a
   `databricks_postgres` database. You don't need to create tables — the app
   does that itself.

## 2. Create the app

1. Open the app switcher → **Databricks Apps** → **+ Create app** →
   **Create a custom app**.
2. In **Configure Git**, enter `https://github.com/IvoWoertman/stock_checker`
   (or your fork), choose **GitHub**, and set the branch to `main`.
   Public repositories do not need a Git credential.

## 3. Attach the Lakebase database resource

1. In the **App resources** section, click **+ Add resource** → **Database**.
2. Select your Lakebase **project**, **branch** (`production`), and
   **database** (`databricks_postgres`).
3. Choose permission **Can connect and create**.
4. Keep the default resource key `postgres`.

When you add the resource, Databricks creates a Postgres role for the app's
service principal and injects `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and
`PGPASSWORD` into the runtime. `db.py` uses `psycopg2`, which reads those
automatically.

## 4. Deploy and verify

1. Click **Deploy** and wait for **Running**.
2. Open the app URL and check `/health` returns `{"status": "ok"}`.
3. On first page load the app creates its `stock` schema and tables (idempotent).
4. Add an item, scan a barcode, and use some grams — the app should feel snappy
   (Lakebase scale-to-zero wakes in a second or two, far faster than a SQL
   warehouse cold start).

## 5. Share with the second household member

1. In **Settings → Users**, ensure the second person is a workspace user
   (Free Edition: sign-in is email OTP / Google / Microsoft).
2. On the app's overview, click **Share** and grant them **Can use**.
3. Both open the same app URL; you should see each other's updates.

## 6. Analytics (later)

Register the Lakebase database in Unity Catalog (Catalog Explorer → new catalog
→ type **Lakebase Postgres**) to query the app's tables with Databricks SQL
alongside your lakehouse data, or stream changes into Delta via CDC.

## Troubleshooting

- **`/health` returns a database error:** confirm the Database resource is
  attached (step 3) and the app is redeployed. Check the app's **Environment**
  tab for the `PG*` variables.
- **First query after idle is slow:** Lakebase scales to zero; the first query
  after a long pause takes a few seconds to wake. After that it's fast.
- **App stops after ~24 hours (Free Edition):** restart it from the app's
  overview, or set up the keep-alive Job described in PLAN.md.
