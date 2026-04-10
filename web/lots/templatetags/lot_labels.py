from django import template


register = template.Library()


LOT_STATUS_LABELS = {
    "APPLICATIONS_SUBMISSION": "Приём заявок",
}

USER_STATUS_LABELS = {
    "NEW": "Новый",
    "REVIEW": "На проверке",
    "PLAN": "К планированию",
    "APPLIED": "Заявка подана",
    "BIDDING": "Участие в торгах",
    "WON": "Выигран",
    "LOST": "Проигран",
    "SKIPPED": "Пропущен",
    "ARCHIVE": "Архив",
}

PARTICIPATION_TYPE_LABELS = {
    "auction": "Торги",
    "application": "Подача заявки",
    "none": "Нет участия",
}

PARTICIPATION_SOURCE_LABELS = {
    "auction_site": "Площадка торгов",
    "application_portal": "Портал подачи заявки",
    "pre_auction_no_url": "Без ссылки",
    "unknown": "Не определено",
}

DEAL_TYPE_LABELS = {
    "sale": "Продажа",
    "rent": "Аренда",
}

CURRENCY_LABELS = {
    "643": "руб.",
    "RUB": "руб.",
    "RUR": "руб.",
}


def _label_for(value, mapping):
    if value in (None, ""):
        return value
    return mapping.get(str(value), value)


@register.filter
def lot_status_label(value):
    return _label_for(value, LOT_STATUS_LABELS)


@register.filter
def user_status_label(value):
    return _label_for(value, USER_STATUS_LABELS)


@register.filter
def participation_type_label(value):
    return _label_for(value, PARTICIPATION_TYPE_LABELS)


@register.filter
def participation_source_label(value):
    return _label_for(value, PARTICIPATION_SOURCE_LABELS)


@register.filter
def deal_type_label(value):
    return _label_for(value, DEAL_TYPE_LABELS)


@register.filter
def currency_label(value):
    return _label_for(value, CURRENCY_LABELS)
