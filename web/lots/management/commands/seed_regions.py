from django.core.management.base import BaseCommand
from django.db.models import Max

from lots.models import Region


REGION_SEED_DATA = (
    {
        "name": "Москва",
        "slug": "moskva",
        "torgi_region_code": 78,
        "subject_rf_code": "77",
        "is_active": True,
        "sort_order": 10,
    },
    {
        "name": "Московская область",
        "slug": "moskovskaya-oblast",
        "torgi_region_code": 53,
        "subject_rf_code": "50",
        "is_active": True,
        "sort_order": 20,
    },
    {
        "name": "Тульская область",
        "slug": "tulskaya-oblast",
        "torgi_region_code": 73,
        "subject_rf_code": "71",
        "is_active": True,
        "sort_order": 30,
    },
    {
        "name": "Калужская область",
        "slug": "kaluzhskaya-oblast",
        "torgi_region_code": 44,
        "subject_rf_code": "40",
        "is_active": True,
        "sort_order": 40,
    },
    {
        "name": "Ленинградская область",
        "slug": "leningradskaya-oblast",
        "torgi_region_code": 50,
        "subject_rf_code": "47",
        "is_active": True,
        "sort_order": 50,
    },
    {
        "name": "Тверская область",
        "slug": "tverskaya-oblast",
        "torgi_region_code": 69,
        "subject_rf_code": "69",
        "is_active": True,
        "sort_order": 60,
    },
    {
        "name": "Ростовская область",
        "slug": "rostovskaya-oblast",
        "torgi_region_code": 61,
        "subject_rf_code": "61",
        "is_active": True,
        "sort_order": 70,
    },
)


class Command(BaseCommand):
    help = "Seed the minimal region directory used by lot filtering."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        next_id = (Region.objects.aggregate(max_id=Max("id")).get("max_id") or 0) + 1

        for payload in REGION_SEED_DATA:
            region = Region.objects.filter(slug=payload["slug"]).first()
            if region is None:
                Region.objects.create(id=next_id, **payload)
                next_id += 1
                created += 1
            else:
                for field, value in payload.items():
                    setattr(region, field, value)
                region.save(update_fields=list(payload.keys()))
                updated += 1

        self.stdout.write(f"created={created}")
        self.stdout.write(f"updated={updated}")
