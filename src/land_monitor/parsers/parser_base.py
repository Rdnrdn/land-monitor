"""Base parser workflow for land-monitor sources."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from land_monitor.crud import create_source_run, get_source_by_code
from land_monitor.db import SessionLocal
from land_monitor.models import Source
from land_monitor.models import SourceRun


class BaseParser:
    source_code = ""
    source_name = ""

    def fetch(self) -> Any:
        raise NotImplementedError

    def parse(self, raw_data: Any) -> list[dict[str, Any]]:
        raise NotImplementedError

    def save(
        self,
        db: Any,
        source: Source,
        source_run: SourceRun,
        parsed_data: list[dict[str, Any]],
    ) -> Any:
        raise NotImplementedError

    def run(self) -> dict[str, Any]:
        db = SessionLocal()
        source_run: SourceRun | None = None

        try:
            source = get_source_by_code(db, self.source_code)
            if source is None:
                raise ValueError(f"Source with code '{self.source_code}' was not found.")

            source_run = create_source_run(
                db,
                source_id=source.id,
                status="pending",
                started_at=datetime.utcnow(),
                message=f"{self.source_name or self.source_code} parser started",
            )

            raw_data = self.fetch()
            parsed_data = self.parse(raw_data)
            save_result = self.save(db, source, source_run, parsed_data)

            source_run.status = "success"
            source_run.finished_at = datetime.utcnow()
            source_run.message = f"Processed {len(parsed_data)} items successfully."
            db.commit()
            db.refresh(source_run)

            return {
                "status": "success",
                "source_run_id": source_run.id,
                "items_count": len(parsed_data),
                "save_result": save_result,
            }
        except Exception as exc:
            if source_run is not None:
                source_run.status = "failed"
                source_run.finished_at = datetime.utcnow()
                source_run.message = str(exc)
                db.commit()
            raise
        finally:
            db.close()
