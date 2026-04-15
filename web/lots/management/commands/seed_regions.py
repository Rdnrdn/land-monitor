from django.core.management.base import BaseCommand

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
)


class Command(BaseCommand):
    help = "Seed the minimal region directory used by lot filtering."

    def handle(self, *args, **options):
        created = 0
        updated = 0

        for payload in REGION_SEED_DATA:
            _, was_created = Region.objects.update_or_create(
                slug=payload["slug"],
                defaults=payload,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(f"created={created}")
        self.stdout.write(f"updated={updated}")
