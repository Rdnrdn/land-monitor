"""Run the stub Torgi.gov.ru parser."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from land_monitor.parsers.torgi_gov import TorgiGovParser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = TorgiGovParser()

    try:
        result = parser.run()
        print(f"[OK] Parser completed: source_run_id={result['source_run_id']}, items_count={result['items_count']}")
        print(f"url={parser.last_request_url}")
        print(f"received_count={parser.last_received_count}")
        print("examples=")
        print(json.dumps(parser.last_parsed_examples[:3], ensure_ascii=False, indent=2, default=str))
        print(f"saved={result['save_result']['saved']}")
        print(f"updated={result['save_result']['updated']}")
        print(f"price_history_created={result['save_result']['price_history_created']}")
        return 0
    except Exception as exc:
        print(f"[ERROR] Parser failed: {exc}")
        print(f"url={parser.last_request_url}")
        print(f"received_count={parser.last_received_count}")
        print("examples=[]")
        print("saved=0")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
