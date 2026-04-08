"""CLI wrapper for Telegram-friendly command outputs."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from land_monitor.bot_commands import cmd_auction, cmd_cheapest, cmd_recent, cmd_runs, cmd_status


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: run_bot_command.py <status|recent|cheapest|auction|runs> [args]")
        return 1

    command = argv[1]

    if command == "status":
        print(cmd_status())
        return 0

    if command == "recent":
        limit = int(argv[2]) if len(argv) > 2 else 5
        print(cmd_recent(limit=limit))
        return 0

    if command == "cheapest":
        limit = int(argv[2]) if len(argv) > 2 else 5
        region = argv[3] if len(argv) > 3 else None
        print(cmd_cheapest(limit=limit, region=region))
        return 0

    if command == "auction":
        if len(argv) < 3:
            print("Usage: run_bot_command.py auction <auction_id>")
            return 1
        print(cmd_auction(int(argv[2])))
        return 0

    if command == "runs":
        limit = int(argv[2]) if len(argv) > 2 else 5
        print(cmd_runs(limit=limit))
        return 0

    print(f"Unknown command: {command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
