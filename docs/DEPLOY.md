# Deploy the Stock Tracker to Databricks

Step-by-step checklist to get the app running in your workspace, validate the
lakehouse connection, and share it with the second household member.

## Prerequisites

- A Databricks workspace (Free Edition works for learning, with the 24-hour
  app stop noted in PLAN.md).
- A **serverless SQL warehouse** in that workspace (Free Edition provides one,
  limited to 2X-Small).

## 1. Create the schema

1. In the workspace sidebar, open **SQL Editor**.
2. Confirm a warehouse is selected at the top-right.
3. Paste the contents of [`sql/schema.sql`](sql/schema.sql) and run it. This
   creates `main.stock` with the three managed Delta tables and the stock view.
4. Optionally run [`sql/seed.sql`](sql/seed.sql) to add two sample items.
5. Sanity-check the view:

   ```sql
   SELECT * FROM main.stock.v_current_lot_stock;
   ```

> If you use a catalog/schema other than `main.stock`, change the names in
> the SQL files and set `DATABRICKS_CATALOG` / `DATABRICKS_SCHEMA` for the app
> (add them to `app.yaml`).

## 2. Create the app

1. In the sidebar, click the **app switcher** and select **Databricks Apps**.
2. Click **+ Create app** → **Create a custom app**.
3. In **Configure Git**, enter `https://github.com/IvoWoertman/stock_checker`
   (or your fork), choose **GitHub**, and set the branch to `main`.
   Public repositories do not need a Git credential.
4. Continue to the **App resources** step (see next section).

## 3. Attach the SQL warehouse resource

1. In **App resources**, click **+ Add resource** → **SQL warehouse**.
2. Select your serverless warehouse.
3. Choose permission **Can use** (not Can manage).
4. Keep the default resource key `sql-warehouse` (the `app.yaml` `valueFrom`
   already references it).

The app's `app.yaml` maps this to `DATABRICKS_WAREHOUSE_ID`, and `db.py`
builds the connection from it plus the workspace hostname and the service
principal's OAuth credentials that Databricks injects automatically.

## 4. Grant data access to the app's service principal

Databricks creates a service principal for the app. It needs Unity Catalog
access to the tables and compute access to the warehouse. If the deployment's
authorization review offers to grant these, accept it; otherwise grant them in
Catalog Explorer:

1. Open **Catalog** (Catalog Explorer) and find `main` → `stock`.
2. On the `stock` schema, open **Permissions**.
3. Grant the app's service principal (search by the app name):
   - `USE SCHEMA` (and `USE CATALOG` on `main`)
   - `SELECT` (to read tables and the view)
   - `MODIFY` (to insert/update event rows)
4. Confirm the service principal has **Can use** on the SQL warehouse
   (this is set in step 3).

## 5. Deploy and verify

1. Click **Deploy** and wait for the status to become **Running**.
2. Open the app URL and check `/health` returns `{"status": "ok"}`.
3. In the UI, add an item (e.g. "Ground beef", 500 g), then use some grams and
   confirm the amount drops.

Things to verify in this first run (milestone-1 spike):

- **Atomicity:** trigger an error (e.g. use more grams than remain) and confirm
  the lot was not partially written.
- **Transaction mechanics:** `service.atomic()` uses `autocommit=False` with the
  SQL connector. If multi-table atomicity is not honored, switch it to explicit
  `BEGIN TRANSACTION … COMMIT` (or `BEGIN ATOMIC … END`). This is the main thing
  the spike exists to validate.
- **Port binding:** `app.yaml` starts gunicorn on
  `${DATABRICKS_APP_PORT:-8080}`. If the app does not come up, confirm the port
  variable name in the app's **Environment** tab.

## 6. Share with the second household member

1. In **Settings → Users**, ensure the second person is a user in the workspace
   (Free Edition: sign-in is email OTP / Google / Microsoft).
2. On the app's overview, click **Share** and grant them **Can use**.
3. Both of you open the same app URL; you should see each other's updates.

## Troubleshooting

- **`DATABRICKS_SERVER_HOSTNAME` missing:** the app must have a SQL warehouse
  resource attached (step 3) for Databricks to inject the connection details.
- **Invalid access token / permission denied:** re-check the service principal
  privileges in step 4 (`USE`/`SELECT`/`MODIFY` on the schema, `Can use` on the
  warehouse).
- **App stops after ~24 hours (Free Edition):** restart it from the app's
  overview, or set up the keep-alive Job described in PLAN.md.
