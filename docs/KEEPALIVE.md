# Keep-alive job

Free Edition automatically stops a Databricks App after ~24 hours. This page
describes the optional scheduled Job that restarts it, so the app is available
without manually restarting.

> This works around a Free Edition fair-use limit. See PLAN.md "Keep-alive
> decision" for the risk. It keeps the app convenient, but Free Edition still
> has no SLA and can shut down compute under its fair-use policy.

## What the job does

`keepalive.py` stops and restarts the app, which resets the 24-hour timer (the
Free Edition limit counts from when an app is "started, updated, or redeployed").

## Create the job

1. Upload `keepalive.py` to your workspace (e.g. drag it into the workspace
   files, or paste it into a notebook).

2. In the workspace sidebar, go to **Workflows** (Jobs) → **Create job**.

3. Add a task:
   - **Type:** Python script (or Notebook, if you pasted the code into one).
   - **Source:** the uploaded `keepalive.py`.
   - Leave parameters empty (it defaults to app name `stockchecker`).

4. Under **Schedule**, set a trigger to run daily (e.g. cron
   `0 3 * * *` for 03:00 UTC). A single daily run is enough — the limit is
   24 hours, so a ~23-hour cadence is ideal; daily is simpler and safe.

5. **Run now** once to confirm it works, then check the run output says
   `App 'stockchecker' restarted.`

## Permissions

The job runs as your identity, which owns the app, so it has permission to
stop/start it. If you later run it as a service principal, that principal needs
`CAN MANAGE` on the app.

## Custom app name

If the app isn't named `stockchecker`, pass the name: set an `APP_NAME`
environment variable on the job task (or edit the default in `keepalive.py`).
