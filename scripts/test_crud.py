"""Smoke test for basic CRUD helpers."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import delete

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from land_monitor.crud import create_source, get_source_by_code
from land_monitor.db import SessionLocal
from land_monitor.models import Source


def main() -> int:
    db = SessionLocal()
    code = "test_source"
    created_for_test = False

    try:
        source = get_source_by_code(db, code)
        if source is None:
            source = create_source(
                db,
                code=code,
                name="Test Source",
                base_url="https://example.com/",
                status="active",
            )
            created_for_test = True
            print(f"[OK] Source created: id={source.id}, code={source.code}")
        else:
            print(f"[OK] Source already exists: id={source.id}, code={source.code}")

        loaded = get_source_by_code(db, code)
        if loaded is None:
            print("[ERROR] Source was not found after create/read check.")
            return 1

        print(f"[OK] Source loaded successfully: id={loaded.id}, name={loaded.name}")
        return 0
    finally:
        if created_for_test:
            db.execute(delete(Source).where(Source.code == code))
            db.commit()
            print(f"[OK] Cleanup completed for source code={code}")
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
