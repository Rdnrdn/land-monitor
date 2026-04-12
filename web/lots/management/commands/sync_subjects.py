from __future__ import annotations

from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from lots.models import Subject


SUBJECTS_ENDPOINT = "https://torgi.gov.ru/new/nsi/v1/SUBJECT"


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class Command(BaseCommand):
    help = "Sync the official RF subjects directory from Torgi NSI SUBJECT."

    def add_arguments(self, parser):
        parser.add_argument(
            "--endpoint",
            default=SUBJECTS_ENDPOINT,
            help=f"Torgi NSI SUBJECT endpoint. Default: {SUBJECTS_ENDPOINT}",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=20.0,
            help="HTTP request timeout in seconds. Default: 20.",
        )

    def handle(self, *args, **options):
        endpoint = options["endpoint"]
        timeout = options["timeout"]

        try:
            response = requests.get(
                endpoint,
                headers={"User-Agent": "land-monitor-subjects-sync/1.0"},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise CommandError(f"Failed to fetch subjects from {endpoint}: {exc}") from exc
        except ValueError as exc:
            raise CommandError(f"Invalid JSON response from {endpoint}: {exc}") from exc

        if not isinstance(payload, list):
            raise CommandError(f"Expected a JSON list from {endpoint}, got {type(payload).__name__}.")

        created = 0
        updated = 0
        skipped = 0
        invalid = 0
        now = timezone.now()

        with transaction.atomic():
            for item in payload:
                if not isinstance(item, dict):
                    invalid += 1
                    continue

                code = _clean_string(item.get("code"))
                name = _clean_string(item.get("name"))
                if not code or not name:
                    invalid += 1
                    continue

                defaults = {
                    "name": name,
                    "okato": _clean_string(item.get("okato")),
                    "published": item.get("published") if isinstance(item.get("published"), bool) else None,
                }

                subject = Subject.objects.filter(code=code).first()
                if subject is None:
                    Subject.objects.create(
                        code=code,
                        created_at=now,
                        updated_at=now,
                        **defaults,
                    )
                    created += 1
                    continue

                changed = [
                    field
                    for field, value in defaults.items()
                    if getattr(subject, field) != value
                ]
                if not changed:
                    skipped += 1
                    continue

                for field in changed:
                    setattr(subject, field, defaults[field])
                subject.updated_at = now
                subject.save(update_fields=[*changed, "updated_at"])
                updated += 1

        self.stdout.write(f"endpoint={endpoint}")
        self.stdout.write(f"received={len(payload)}")
        self.stdout.write(f"created={created}")
        self.stdout.write(f"updated={updated}")
        self.stdout.write(f"skipped={skipped}")
        self.stdout.write(f"invalid={invalid}")
