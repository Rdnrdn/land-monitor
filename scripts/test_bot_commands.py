"""Smoke test for Telegram-friendly command outputs."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from land_monitor.bot_commands import cmd_auction, cmd_cheapest, cmd_recent, cmd_runs, cmd_status


def main() -> int:
    print("=== cmd_status ===")
    print(cmd_status())
    print()

    print("=== cmd_recent ===")
    print(cmd_recent())
    print()

    print("=== cmd_cheapest ===")
    print(cmd_cheapest())
    print()

    print("=== cmd_auction(1) ===")
    print(cmd_auction(1))
    print()

    print("=== cmd_runs ===")
    print(cmd_runs())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
