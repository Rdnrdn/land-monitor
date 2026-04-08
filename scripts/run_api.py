"""Run the land-monitor FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main() -> int:
    uvicorn.run("land_monitor.api:app", host="0.0.0.0", port=8000, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
