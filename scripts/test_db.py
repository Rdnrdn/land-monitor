"""Simple database connectivity check script."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from land_monitor.db import test_connection


def main() -> int:
    ok, message = test_connection()
    if ok:
        print(f"[OK] {message}")
        return 0

    print(f"[ERROR] {message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
