"""Application entrypoint for land-monitor."""

from __future__ import annotations

from land_monitor.db import test_connection


def main() -> int:
    ok, message = test_connection()
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
