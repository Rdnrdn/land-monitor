"""Curated safe municipality filter options for Django UI.

This is a temporary backend layer for Moscow Oblast until canonical
municipality values are materialized in the database. The UI must not expose
raw municipality directory rows directly because that directory still contains
analytically unsafe values and parsing artefacts.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

MOSCOW_OBLAST_SLUG = "moskovskaya-oblast"


def normalize_municipality_name(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = unicodedata.normalize("NFKC", value).strip()
    if not candidate:
        return None
    candidate = candidate.replace("Ё", "Е").replace("ё", "е")
    candidate = re.sub(r"\s+", " ", candidate)
    return candidate.lower()


def slugify_municipality_name(value: str) -> str:
    candidate = normalize_municipality_name(value) or ""
    candidate = re.sub(r"[^0-9a-zа-я]+", "-", candidate)
    candidate = re.sub(r"-{2,}", "-", candidate).strip("-")
    return candidate or "municipality"


@dataclass(frozen=True)
class SafeMunicipalityOption:
    label: str
    aliases: tuple[str, ...]

    @property
    def value(self) -> str:
        return slugify_municipality_name(self.label)

    @property
    def slug(self) -> str:
        return self.value

    @property
    def name(self) -> str:
        return self.label

    @property
    def normalized_aliases(self) -> tuple[str, ...]:
        return tuple(
            normalized
            for normalized in (
                normalize_municipality_name(alias)
                for alias in self.aliases
            )
            if normalized
        )


CURATED_MOSCOW_OBLAST_MUNICIPALITIES: tuple[SafeMunicipalityOption, ...] = (
    SafeMunicipalityOption("Богородский", (
        "Ногинский район",
        "Городской округ БОГОРОДСКИЙ",
        "Городской округ для ИЖС в Богородском",
        "Городской округ для ЛПХ в Богородском",
        "Городской округ под производственную деятельность в Богородском",
    )),
    SafeMunicipalityOption("Волоколамский", (
        "Волоколамский район",
        "Муниципальный округ Волоколамский",
        "Муниципальный округ для ИЖС в Волоколамском",
        "Муниципальный округ для ЛПХ в Волоколамском",
        "Муниципальный округ под магазины в Волоколамском",
    )),
    SafeMunicipalityOption("Воскресенск", (
        "Воскресенский район",
        "Городской округ Воскресенск",
    )),
    SafeMunicipalityOption("Дмитровский", (
        "Дмитровский район",
        "Городской округ Дмитровский",
        "Муниципальный округ Дмитровский",
        "Городской округ для ИЖС в Дмитровском",
        "Муниципальный округ для ИЖС в Дмитровском",
        "Муниципальный округ для ЛПХ в Дмитровском",
        "Городской округ под спорт в Дмитровском",
        "Городской округ под ремонт автомобилей в Дмитровском",
        "Муниципальный округ под ведение садоводства в Дмитровском",
        "Муниципальный округ под ремонт автомобилей в Дмитровском",
        "Муниципальный округ под объекты дорожного сервиса в Дмитровском",
    )),
    SafeMunicipalityOption("Домодедово", (
        "Городской округ Домодедово",
    )),
    SafeMunicipalityOption("Дубна", (
        "Городской округ Дубна",
    )),
    SafeMunicipalityOption("Егорьевск", (
        "Городской округ Егорьевск",
        "Муниципальный округ Егорьевск",
    )),
    SafeMunicipalityOption("Зарайск", (
        "Муниципальный округ Зарайск",
    )),
    SafeMunicipalityOption("Истра", (
        "Истринский район",
        "Городской округ Истра",
        "Муниципальный округ Истра",
    )),
    SafeMunicipalityOption("Кашира", (
        "Городской округ Кашира",
    )),
    SafeMunicipalityOption("Клин", (
        "Городской округ Клин",
    )),
    SafeMunicipalityOption("Коломна", (
        "Коломенский район",
        "Городской округ Коломна",
    )),
    SafeMunicipalityOption("Котельники", (
        "Котельники",
    )),
    SafeMunicipalityOption("Красногорск", (
        "Городской округ Красногорск",
    )),
    SafeMunicipalityOption("Ленинский", (
        "Городской округ Ленинский",
        "Ленинский муниципальный район",
    )),
    SafeMunicipalityOption("Лобня", (
        "Городской округ Лобня",
    )),
    SafeMunicipalityOption("Лосино-Петровский", (
        "Городской округ Лосино-Петровский",
        "Городской округ Лосино-Петровский Земельный участок Земельный участок",
    )),
    SafeMunicipalityOption("Лотошино", (
        "Муниципальный округ Лотошино",
    )),
    SafeMunicipalityOption("Луховицы", (
        "Городской округ Луховицы",
        "Муниципальный округ Луховицы",
    )),
    SafeMunicipalityOption("Люберцы", (
        "Городской округ Люберцы",
    )),
    SafeMunicipalityOption("Можайский", (
        "Можайский район",
        "Городской округ Можайск",
        "Городской округ Можайский",
        "Муниципальный округ Можайский",
        "Муниципальный округ для ИЖС в Можайском",
        "Муниципальный округ для ЛПХ в Можайском",
    )),
    SafeMunicipalityOption("Молодёжный", (
        "Городской округ Молодёжный",
    )),
    SafeMunicipalityOption("Наро-Фоминский", (
        "Городской округ Наро-Фоминский",
        "Наро-Фоминск",
        "Городской округ для ИЖС в Наро-Фоминском",
        "Городской округ для ЛПХ в Наро-Фоминском",
        "Городской округ для ведения личного подсобного хозяйства в Наро-Фоминском",
        "Городской округ под выращивание зерновых и иных сельскохозяйственных культур в Наро-Фоминском",
    )),
    SafeMunicipalityOption("Одинцовский", (
        "Городской округ Одинцовский",
        "Городской округ Спорт в Одинцовском",
        "Городской округ для ИЖС в Одинцовском",
        "Городской округ м для ИЖС в Одинцовском",
    )),
    SafeMunicipalityOption("Орехово-Зуевский", (
        "Городской округ Орехово-Зуевский",
        "Городской округ для ИЖС в Орехово-Зуевском",
        "Городской округ для ЛПХ в Орехово-Зуевском",
        "Городской округ под производственную деятельность в Орехово-Зуевском",
    )),
    SafeMunicipalityOption("Павлово-Посадский", (
        "Городской округ Павловский Посад",
        "Городской округ для ИЖС в Павлово-Посадском",
        "Городской округ для ЛПХ в Павлово-Посадском",
        "Городской округ склады в Павлово-Посадском",
    )),
    SafeMunicipalityOption("Подольск", (
        "Городской округ Подольск",
    )),
    SafeMunicipalityOption("Пушкинский", (
        "Городской округ ПУШКИНСКИЙ",
        "Городской округ Пушкинский",
        "Городской округ для ИЖС в Пушкинском",
        "Городской округ для ЛПХ в Пушкинском",
    )),
    SafeMunicipalityOption("Раменский", (
        "Раменский район",
        "Городской округ Раменский",
        "Муниципальный округ Раменский",
        "Муниципальный округ для ИЖС в Раменском",
        "Муниципальный округ для ЛПХ в Раменском",
        "Муниципальный округ м для ЛПХ в Раменском",
        "Муниципальный округ под ведение садоводства в Раменском",
        "Муниципальный округ под производственную деятельность в Раменском",
    )),
    SafeMunicipalityOption("Рузский", (
        "Муниципальный округ Рузский",
        "Городской округ ЛПХ в Рузском",
        "Муниципальный округ ЛПХ в Рузском",
        "Городской округ для ЛПХ в Рузском",
        "Муниципальный округ для ЛПХ в Рузском",
        "Муниципальный округ для ИЖС в Рузском",
        "Муниципальный округ склады в Рузском",
        "Городской округ под склад в Рузском",
    )),
    SafeMunicipalityOption("Серебряные Пруды", (
        "Городской округ Серебряные Пруды",
        "Муниципальный округ Серебряные Пруды",
        "Серебряно-Прудский район",
    )),
    SafeMunicipalityOption("Сергиево-Посадский", (
        "Городской округ Сергиево-Посадский",
        "Сергиево-Посадский район",
        "Городской округ для ИЖС в Сергиево-Посадском",
        "Городской округ для ЛПХ в Сергиево-Посадском",
    )),
    SafeMunicipalityOption("Серпухов", (
        "Серпуховский район",
        "Городской округ СЕРПУХОВ",
        "Городской округ Серпухов",
    )),
    SafeMunicipalityOption("Солнечногорск", (
        "Солнечногорский район",
        "Городской округ Солнечногорск",
    )),
    SafeMunicipalityOption("Ступино", (
        "Ступинский район",
        "Городской округ Ступино",
        "Городской округ Ступино р",
    )),
    SafeMunicipalityOption("Талдомский", (
        "Талдомский район",
        "Городской округ Талдомский",
        "Городской округ для ИЖС в Талдомском",
        "Городской округ для ЛПХ в Талдомском",
        "Городской округ м для ИЖС в Талдомском",
        "Городской округ м для ЛПХ в Талдомском",
        "Городской округ под ведение садоводства в Талдомском",
        "Городской округ м под ведение садоводства в Талдомском",
    )),
    SafeMunicipalityOption("Химки", (
        "Городской округ Химки",
    )),
    SafeMunicipalityOption("Чехов", (
        "Городской округ Чехов",
        "Муниципальный округ Чехов",
    )),
    SafeMunicipalityOption("Шатура", (
        "Муниципальный округ Шатура",
        "Городской округ Шатура Российская Федерация",
    )),
    SafeMunicipalityOption("Шаховская", (
        "Городской округ Шаховская",
        "Муниципальный округ Шаховская",
    )),
    SafeMunicipalityOption("Щелково", (
        "Щелковский район",
        "Городской округ Щелково",
        "Городской округ Щёлково",
    )),
    SafeMunicipalityOption("Электросталь", (
        "Городской округ Электросталь",
    )),
)


@lru_cache(maxsize=1)
def moscow_oblast_safe_option_map() -> dict[str, SafeMunicipalityOption]:
    return {option.value: option for option in CURATED_MOSCOW_OBLAST_MUNICIPALITIES}


@lru_cache(maxsize=1)
def moscow_oblast_safe_normalized_alias_map() -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for option in CURATED_MOSCOW_OBLAST_MUNICIPALITIES:
        for alias in option.normalized_aliases:
            alias_map[alias] = option.value
    return alias_map


@lru_cache(maxsize=1)
def moscow_oblast_safe_raw_alias_map() -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for option in CURATED_MOSCOW_OBLAST_MUNICIPALITIES:
        for alias in option.aliases:
            alias_map[alias] = option.value
    return alias_map


def get_safe_municipality_options_for_region_slug(region_slug: str) -> list[SafeMunicipalityOption]:
    if region_slug != MOSCOW_OBLAST_SLUG:
        return []
    return list(CURATED_MOSCOW_OBLAST_MUNICIPALITIES)


def get_safe_municipality_label(
    *,
    region_slug: str | None,
    normalized_name: str | None = None,
    raw_name: str | None = None,
) -> str | None:
    if region_slug != MOSCOW_OBLAST_SLUG:
        return None

    option_map = moscow_oblast_safe_option_map()
    if normalized_name:
        safe_value = moscow_oblast_safe_normalized_alias_map().get(normalized_name)
        if safe_value and safe_value in option_map:
            return option_map[safe_value].label

    if raw_name:
        safe_value = moscow_oblast_safe_raw_alias_map().get(raw_name)
        if safe_value and safe_value in option_map:
            return option_map[safe_value].label

    return None
