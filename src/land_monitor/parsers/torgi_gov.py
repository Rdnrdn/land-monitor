"""Conservative first-step parser for torgi.gov.ru."""

from __future__ import annotations

import json
import logging
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests

from land_monitor.crud import create_or_update_auction, create_price_history, get_or_create_plot_by_cadastre
from land_monitor.models import Source, SourceRun
from land_monitor.parsers.parser_base import BaseParser

logger = logging.getLogger(__name__)


class TorgiGovParser(BaseParser):
    source_code = "torgi_gov"
    source_name = "Torgi.gov.ru"

    search_url = "https://torgi.gov.ru/new/api/public/lotcards/search"
    search_method = "GET"
    page_limit = 1
    items_limit = 5
    request_pause_seconds = 1.5
    timeout = (10, 30)
    raw_response_path = Path("data/torgi_gov_last_response.json")
    user_agent = (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 land-monitor/0.1"
    )

    def __init__(self) -> None:
        self.last_request_url: str | None = None
        self.last_request_method: str | None = None
        self.last_request_payload: dict[str, Any] | None = None
        self.last_received_count = 0
        self.last_parsed_examples: list[dict[str, Any]] = []

    def fetch(self) -> list[dict[str, Any]]:
        session = requests.Session()
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://torgi.gov.ru/new/public/lots/reg",
            "User-Agent": self.user_agent,
        }

        collected_items: list[dict[str, Any]] = []

        for page in range(self.page_limit):
            params = {
                "page": page,
                "size": self.items_limit,
                "sort": "firstVersionPublicationDate,desc",
            }
            self.last_request_method = self.search_method
            self.last_request_url = self.search_url
            self.last_request_payload = params

            try:
                response = session.get(
                    self.search_url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                self._save_raw_response(
                    {
                        "error": str(exc),
                        "method": self.search_method,
                        "url": self.search_url,
                        "page": page,
                        "params": params,
                    }
                )
                raise

            response_json = response.json()
            self._save_raw_response(response_json)

            page_items = self._extract_items(response_json)
            self.last_received_count = len(page_items)
            logger.info(
                "Torgi.gov response received from %s: %s records on page %s",
                self.search_url,
                len(page_items),
                page + 1,
            )

            if not page_items:
                break

            remaining = self.items_limit - len(collected_items)
            collected_items.extend(page_items[:remaining])

            time.sleep(self.request_pause_seconds)

            if len(collected_items) >= self.items_limit:
                break

        return collected_items[: self.items_limit]

    def parse(self, raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        parsed_items: list[dict[str, Any]] = []
        for item in raw_data[: self.items_limit]:
            external_id = self._pick_first(item, ["id", "lotId", "lotNumber", "noticeNumber"])
            if external_id is None:
                continue

            area = self._normalize_decimal(
                self._pick_first(
                    item,
                    [
                        "area",
                        "lotArea",
                        "square",
                        "landArea",
                        "characteristics.area",
                    ],
                )
            )

            area_sotka = None
            if area is not None:
                area_sotka = (area / Decimal("100")).quantize(Decimal("0.01"))

            parsed_items.append(
                {
                    "external_id": str(external_id),
                    "region": self._extract_region(item) or "Unknown region",
                    "start_price": self._normalize_decimal(
                        self._pick_first(
                            item,
                            [
                                "priceMin",
                                "startPrice",
                                "biddStartPrice",
                                "initialPrice",
                            ],
                        )
                    ),
                    "status": str(
                        self._pick_first(item, ["status", "lotStatus", "statusCode"]) or "unknown"
                    ),
                    "source_url": self._build_source_url(item, external_id),
                    "area": area,
                    "area_sotka": area_sotka,
                    "cadastre_number": self._extract_cadastre_number(item),
                    "raw_json": item,
                }
            )

        self.last_parsed_examples = parsed_items[:3]
        return parsed_items

    def save(
        self,
        db: Any,
        source: Source,
        source_run: SourceRun,
        parsed_data: list[dict[str, Any]],
    ) -> dict[str, Any]:
        saved = 0
        updated = 0
        price_history_created = 0

        for item in parsed_data[: self.items_limit]:
            start_price = item.get("start_price")
            area_sotka = item.get("area_sotka")
            price_per_sotka = None
            if start_price is not None and area_sotka not in (None, 0):
                price_per_sotka = Decimal(str(start_price)) / Decimal(str(area_sotka))

            plot = get_or_create_plot_by_cadastre(
                db,
                cadastre_number=item.get("cadastre_number"),
                source_id=source.id,
                region=item["region"],
                area=item.get("area"),
                area_sotka=item.get("area_sotka"),
                title=item["raw_json"].get("title"),
                status="new",
            )

            auction, created = create_or_update_auction(
                db,
                source_id=source.id,
                plot_id=plot.id if plot is not None else None,
                source_run_id=source_run.id,
                external_id=item["external_id"],
                source_url=item.get("source_url"),
                region=item.get("region"),
                start_price=start_price,
                current_price=start_price,
                price_per_sotka=price_per_sotka,
                status=item.get("status", "published"),
                raw_json=item.get("raw_json"),
            )

            if created:
                saved += 1
            else:
                updated += 1

            if start_price is not None:
                _, created_price_history = create_price_history(
                    db,
                    source_type="auction",
                    source_id=source.id,
                    auction_id=auction.id,
                    price=start_price,
                )
                if created_price_history:
                    price_history_created += 1

        return {
            "saved": saved,
            "updated": updated,
            "price_history_created": price_history_created,
        }

    def _save_raw_response(self, payload: Any) -> None:
        self.raw_response_path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_response_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _extract_items(self, response_json: Any) -> list[dict[str, Any]]:
        if isinstance(response_json, list):
            return [item for item in response_json if isinstance(item, dict)]

        if not isinstance(response_json, dict):
            return []

        for key in ("content", "items", "results", "list"):
            value = response_json.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        return []

    def _pick_first(self, payload: Any, paths: list[str]) -> Any:
        for path in paths:
            value = self._get_path(payload, path)
            if value not in (None, "", []):
                return value
        return None

    def _get_path(self, payload: Any, path: str) -> Any:
        current = payload
        for part in path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    def _extract_region(self, item: dict[str, Any]) -> str | None:
        region = self._pick_first(
            item,
            [
                "region",
                "regionName",
                "subjectRfName",
                "rfSubject",
                "location.region",
                "location.subjectRfName",
            ],
        )
        if region is not None:
            return str(region)

        location = item.get("location")
        if isinstance(location, dict):
            for value in location.values():
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return None

    def _extract_cadastre_number(self, item: dict[str, Any]) -> str | None:
        direct_value = self._pick_first(
            item,
            [
                "cadastreNumber",
                "cadastralNumber",
                "landCadastreNumber",
                "characteristics.cadastreNumber",
            ],
        )
        if direct_value is not None:
            return str(direct_value)

        characteristics = item.get("characteristics")
        if isinstance(characteristics, list):
            for char_item in characteristics:
                if not isinstance(char_item, dict):
                    continue
                name = str(char_item.get("name") or char_item.get("code") or "").lower()
                if "кадастр" in name or "cadastr" in name:
                    value = char_item.get("value")
                    if value:
                        return str(value)

        return None

    def _build_source_url(self, item: dict[str, Any], external_id: Any) -> str:
        explicit_url = self._pick_first(item, ["url", "lotUrl", "href"])
        if explicit_url is not None:
            return str(explicit_url)
        return f"https://torgi.gov.ru/new/public/lots/lot/{external_id}"

    def _normalize_decimal(self, value: Any) -> Decimal | None:
        if value in (None, ""):
            return None

        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))

        if isinstance(value, (int, float)):
            return Decimal(str(value)).quantize(Decimal("0.01"))

        if isinstance(value, str):
            normalized = value.replace(" ", "").replace(",", ".")
            try:
                return Decimal(normalized).quantize(Decimal("0.01"))
            except InvalidOperation:
                return None

        return None
