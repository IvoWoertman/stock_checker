"""Keep-alive job for the Databricks App.

Free Edition stops an app after ~24 hours. Run this script as a scheduled
Databricks Job every ~23 hours; it restarts the app, which resets the timer.
The job runs under your workspace identity (which owns the app), so it can
stop/start it. See docs/KEEPALIVE.md for setup.

Note: this deliberately works around a Free Edition fair-use limit. Treat it as
a convenience, not a reliability guarantee (see PLAN.md "Keep-alive decision").
"""
import os
from contextlib import suppress

from databricks.sdk import WorkspaceClient

APP_NAME = os.environ.get("APP_NAME", "stockchecker")


def main() -> None:
    client = WorkspaceClient()
    with suppress(Exception):
        client.apps.stop_and_wait(name=APP_NAME)
    client.apps.start_and_wait(name=APP_NAME)
    print(f"App '{APP_NAME}' restarted.")


if __name__ == "__main__":
    main()
