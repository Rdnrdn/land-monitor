from __future__ import annotations

from django.core.management.base import BaseCommand

from land_monitor.db import SessionLocal
from land_monitor.models import Lot
from lots.models import Region

from .fetch_lots_mo import fetch_region_lots


class Command(BaseCommand):
    help = (
        "Fetch lots from torgi.gov.ru using the regions directory. "
        "Default mode is a bounded safe pass over all active regions. "
        "Use --dry-run to print the plan only, --region-slug to target one region, "
        "and --full-scan to continue until the source reports the last page."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the execution plan only. No requests to torgi.gov.ru and no DB writes.",
        )
        parser.add_argument(
            "--region-slug",
            help="Load one specific region from the regions directory by slug, for example moskva.",
        )
        parser.add_argument(
            "--full-scan",
            action="store_true",
            help="Disable bounded limits and continue until each selected region reaches the last page.",
        )
        parser.add_argument(
            "--limit-per-region",
            type=int,
            default=150,
            help="Bounded mode only: max lots to ingest per selected region. Default: 150.",
        )
        parser.add_argument(
            "--start-page",
            type=int,
            default=0,
            help="Page offset for the selected region set. Default: 0.",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=20,
            help="Bounded mode only: max pages to fetch per selected region. Default: 20.",
        )

    def handle(self, *args, **options):
        region_slug = options.get("region_slug")

        active_regions_qs = Region.objects.filter(is_active=True).order_by("sort_order", "id")
        if region_slug:
            active_regions_qs = active_regions_qs.filter(slug=region_slug)

        active_regions = list(active_regions_qs)
        if not active_regions:
            if region_slug:
                self.stdout.write(f"active_regions=0 region_slug={region_slug}")
            else:
                self.stdout.write("active_regions=0")
            return

        self.stdout.write(f"active_regions={len(active_regions)}")
        if region_slug:
            self.stdout.write(f"selected_region_slug={region_slug}")
        for index, region in enumerate(active_regions, start=1):
            self.stdout.write(
                f"plan[{index}] id={region.id} name={region.name} "
                f"slug={region.slug} torgi_region_code={region.torgi_region_code} "
                f"sort_order={region.sort_order}"
            )

        if options["dry_run"]:
            self.stdout.write("dry_run=true")
            return

        full_scan = bool(options["full_scan"])
        limit_per_region = None if full_scan else int(options["limit_per_region"])
        start_page = int(options["start_page"])
        max_pages = None if full_scan else int(options["max_pages"])

        self.stdout.write(f"mode={'full_scan' if full_scan else 'bounded'}")
        self.stdout.write(
            f"limits limit_per_region={limit_per_region if limit_per_region is not None else 'unbounded'} "
            f"max_pages={max_pages if max_pages is not None else 'unbounded'} "
            f"start_page={start_page}"
        )

        total_loaded = 0
        inserted = 0
        updated = 0

        for region in active_regions:
            result = fetch_region_lots(
                region_code=str(region.torgi_region_code),
                region_name=region.name,
                stdout=self.stdout,
                limit=limit_per_region,
                start_page=start_page,
                max_pages=max_pages,
            )
            total_loaded += int(result["total_loaded"] or 0)
            inserted += int(result["inserted"] or 0)
            updated += int(result["updated"] or 0)
            self.stdout.write(
                f"region_done name={result['region_name']} code={result['region_code']} "
                f"total_loaded={result['total_loaded']} inserted={result['inserted']} "
                f"updated={result['updated']} pages_processed={result['pages_processed']} "
                f"stop_reason={result['stop_reason']}"
            )

        db = SessionLocal()
        try:
            total_rows_in_db = db.query(Lot).count()
        finally:
            db.close()

        self.stdout.write(f"total_loaded={total_loaded}")
        self.stdout.write(f"inserted={inserted}")
        self.stdout.write(f"updated={updated}")
        self.stdout.write(f"total_rows_in_db={total_rows_in_db}")
