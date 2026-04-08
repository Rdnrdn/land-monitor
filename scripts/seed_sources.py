"""Seed initial source records."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from land_monitor.crud import create_source, get_source_by_code, list_sources
from land_monitor.db import SessionLocal


SEED_SOURCES = [
    {
        "code": "torgi_gov",
        "name": "Torgi.gov.ru",
        "base_url": "https://torgi.gov.ru/",
        "status": "active",
    },
    {
        "code": "avito",
        "name": "Avito",
        "base_url": "https://www.avito.ru/",
        "status": "active",
    },
]


def main() -> int:
    db = SessionLocal()
    created_codes: list[str] = []
    existing_codes: list[str] = []

    try:
        for payload in SEED_SOURCES:
            source = get_source_by_code(db, payload["code"])
            if source is None:
                create_source(db, **payload)
                created_codes.append(payload["code"])
            else:
                existing_codes.append(payload["code"])

        print("Seed completed.")
        print(f"Created: {created_codes or 'none'}")
        print(f"Existing: {existing_codes or 'none'}")
        print(f"Total sources: {len(list_sources(db))}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
