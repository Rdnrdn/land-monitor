"""Basic CRUD helpers for land-monitor."""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from land_monitor.enums import UserLotStatus
from land_monitor.models import Auction, Listing, Lot, Notice, Plot, PriceHistory, Source, SourceRun, UserLot


def _apply_updates(instance: Any, values: dict[str, Any]) -> Any:
    for key, value in values.items():
        setattr(instance, key, value)
    return instance


def _apply_non_empty_updates(instance: Any, values: dict[str, Any]) -> Any:
    for key, value in values.items():
        if value is not None:
            setattr(instance, key, value)
    return instance


def create_source(db: Session, **values: Any) -> Source:
    source = Source(**values)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def get_source_by_code(db: Session, code: str) -> Source | None:
    return db.query(Source).filter(Source.code == code).first()


def list_sources(db: Session) -> list[Source]:
    return db.query(Source).order_by(Source.id.asc()).all()


def create_source_run(db: Session, **values: Any) -> SourceRun:
    source_run = SourceRun(**values)
    db.add(source_run)
    db.commit()
    db.refresh(source_run)
    return source_run


def create_plot(db: Session, **values: Any) -> Plot:
    plot = Plot(**values)
    db.add(plot)
    db.commit()
    db.refresh(plot)
    return plot


def get_or_create_plot_by_cadastre(
    db: Session,
    *,
    cadastre_number: str | None,
    **values: Any,
) -> Plot | None:
    if not cadastre_number:
        return None

    plot = db.query(Plot).filter(Plot.cadastre_number == cadastre_number).first()
    if plot is None:
        plot = Plot(cadastre_number=cadastre_number, **values)
        db.add(plot)
    else:
        _apply_non_empty_updates(plot, values)

    db.commit()
    db.refresh(plot)
    return plot


def create_or_update_auction(db: Session, **values: Any) -> tuple[Auction, bool]:
    source_id = values["source_id"]
    external_id = values["external_id"]
    auction = (
        db.query(Auction)
        .filter(Auction.source_id == source_id, Auction.external_id == external_id)
        .first()
    )

    if auction is None:
        auction = Auction(**values)
        db.add(auction)
        created = True
    else:
        _apply_updates(auction, values)
        created = False

    db.commit()
    db.refresh(auction)
    return auction, created


def create_auction(db: Session, **values: Any) -> Auction:
    auction, _ = create_or_update_auction(db, **values)
    return auction


def create_listing(db: Session, **values: Any) -> Listing:
    source_id = values["source_id"]
    external_id = values["external_id"]
    listing = (
        db.query(Listing)
        .filter(Listing.source_id == source_id, Listing.external_id == external_id)
        .first()
    )

    if listing is None:
        listing = Listing(**values)
        db.add(listing)
    else:
        _apply_updates(listing, values)

    db.commit()
    db.refresh(listing)
    return listing


def create_price_history(db: Session, **values: Any) -> tuple[PriceHistory, bool]:
    auction_id = values.get("auction_id")
    listing_id = values.get("listing_id")
    price = values["price"]

    latest_entry = (
        db.query(PriceHistory)
        .filter(
            or_(
                PriceHistory.auction_id == auction_id if auction_id is not None else False,
                PriceHistory.listing_id == listing_id if listing_id is not None else False,
            )
        )
        .order_by(desc(PriceHistory.recorded_at), desc(PriceHistory.id))
        .first()
    )

    if latest_entry is not None and latest_entry.price == price:
        return latest_entry, False

    price_history = PriceHistory(**values)
    db.add(price_history)
    db.commit()
    db.refresh(price_history)
    return price_history, True


def upsert_lot(db: Session, values: dict[str, Any]) -> Lot:
    insert_stmt = insert(Lot).values(**values)
    update_columns = {
        col.name: insert_stmt.excluded[col.name]
        for col in Lot.__table__.columns
        if col.name not in {"id", "created_at"}
    }
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=["source", "source_lot_id"],
        set_=update_columns,
    ).returning(Lot)
    result = db.execute(stmt).scalar_one()
    db.commit()
    return result


def list_lots_with_user_state(db: Session, limit: int = 200, offset: int = 0) -> list[tuple[Lot, UserLot | None]]:
    return (
        db.query(Lot, UserLot)
        .outerjoin(UserLot, UserLot.lot_id == Lot.id)
        .order_by(Lot.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def list_lots_with_notice(
    db: Session,
    limit: int = 200,
    offset: int = 0,
) -> list[tuple[Lot, Notice | None]]:
    return (
        db.query(Lot, Notice)
        .outerjoin(Notice, Notice.notice_number == Lot.notice_number)
        .order_by(Lot.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def list_user_lots(db: Session, limit: int = 200, offset: int = 0) -> list[UserLot]:
    return db.query(UserLot).order_by(UserLot.id.desc()).offset(offset).limit(limit).all()


def get_user_lot(db: Session, user_lot_id: int) -> UserLot | None:
    return db.query(UserLot).filter(UserLot.id == user_lot_id).first()


def update_user_lot_status(db: Session, user_lot_id: int, status: UserLotStatus) -> UserLot | None:
    lot = get_user_lot(db, user_lot_id)
    if lot is None:
        return None
    lot.user_status = status
    db.commit()
    db.refresh(lot)
    return lot


def toggle_user_lot_favorite(db: Session, user_lot_id: int, is_favorite: bool) -> UserLot | None:
    lot = get_user_lot(db, user_lot_id)
    if lot is None:
        return None
    lot.is_favorite = is_favorite
    db.commit()
    db.refresh(lot)
    return lot


def update_user_lot_comment(db: Session, user_lot_id: int, comment: str | None) -> UserLot | None:
    lot = get_user_lot(db, user_lot_id)
    if lot is None:
        return None
    lot.comment = comment
    db.commit()
    db.refresh(lot)
    return lot


def update_user_lot_flags(
    db: Session,
    user_lot_id: int,
    *,
    needs_inspection: bool | None = None,
    needs_legal_check: bool | None = None,
    deposit_paid: bool | None = None,
) -> UserLot | None:
    lot = get_user_lot(db, user_lot_id)
    if lot is None:
        return None
    if needs_inspection is not None:
        lot.needs_inspection = needs_inspection
    if needs_legal_check is not None:
        lot.needs_legal_check = needs_legal_check
    if deposit_paid is not None:
        lot.deposit_paid = deposit_paid
    db.commit()
    db.refresh(lot)
    return lot
