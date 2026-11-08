"""Nimbus entrypoint, locally and as a Databricks App.

The platform assigns the port in ``DATABRICKS_APP_PORT`` and only routes to
``0.0.0.0``. Locally ``PORT`` works too; the default is 8741.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import uvicorn  # noqa: E402

from nimbus import config  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run("nimbus.api:create_app", factory=True, host="0.0.0.0", port=config.port(), app_dir=str(BACKEND))


if __name__ == "__main__":
    main()
