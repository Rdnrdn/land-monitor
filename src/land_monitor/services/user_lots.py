"""User lot services for land-monitor."""

from __future__ import annotations

from land_monitor.models import UserLot


def serialize_user_lot(lot: UserLot) -> dict[str, object]:
    return {
        "id": lot.id,
        "lot_id": lot.lot_id,
        "user_status": lot.user_status.value if lot.user_status else None,
        "is_favorite": lot.is_favorite,
        "needs_inspection": lot.needs_inspection,
        "needs_legal_check": lot.needs_legal_check,
        "deposit_paid": lot.deposit_paid,
        "comment": lot.comment,
        "created_at": lot.created_at,
        "updated_at": lot.updated_at,
    }
