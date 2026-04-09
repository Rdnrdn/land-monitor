from django.core.management.base import BaseCommand

from land_monitor.db import SessionLocal
from land_monitor.models import Municipality
from land_monitor.services.municipalities import sync_lot_municipality_refs


class Command(BaseCommand):
    help = "Create municipalities from lot municipality_name values and backfill lots.municipality_id."

    def handle(self, *args, **options):
        db = SessionLocal()
        try:
            inserted, matched, cleared = sync_lot_municipality_refs(db)
            db.commit()
            total_municipalities = db.query(Municipality).count()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        self.stdout.write(f"municipalities_synced={total_municipalities}")
        self.stdout.write(f"directory_upserted={inserted}")
        self.stdout.write(f"lots_matched={matched}")
        self.stdout.write(f"lots_cleared={cleared}")
