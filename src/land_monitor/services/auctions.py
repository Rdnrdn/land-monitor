"""Read-oriented services for auctions and parser runs."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from land_monitor.models import Auction, Plot, PriceHistory, SourceRun
from land_monitor.services.public_views import (
    auction_card_public_view,
    auction_public_view,
    parser_run_public_view,
)
from land_monitor.services.serializers import (
    serialize_auction,
    serialize_plot,
    serialize_price_history,
    serialize_source_run,
)


def list_auctions(
    db: Session,
    limit: int = 50,
    region: str | None = None,
    status: str | None = None,
    order_by: str = "id",
) -> list[dict[str, object]]:
    query = db.query(Auction)

    if region:
        query = query.filter(Auction.region == region)
    if status:
        query = query.filter(Auction.status == status)

    order_column = getattr(Auction, order_by, Auction.id)
    query = query.order_by(order_column.desc() if order_by == "id" else order_column).limit(limit)
    return [serialize_auction(auction) for auction in query.all()]


def get_auction_by_id(db: Session, auction_id: int) -> dict[str, object] | None:
    auction = db.query(Auction).filter(Auction.id == auction_id).first()
    if auction is None:
        return None

    plot = db.query(Plot).filter(Plot.id == auction.plot_id).first() if auction.plot_id else None
    price_history = (
        db.query(PriceHistory)
        .filter(PriceHistory.auction_id == auction.id)
        .order_by(PriceHistory.recorded_at.desc(), PriceHistory.id.desc())
        .all()
    )

    return {
        "auction": serialize_auction(auction),
        "plot": serialize_plot(plot),
        "price_history": [serialize_price_history(item) for item in price_history],
    }


def list_recent_auctions(db: Session, limit: int = 10) -> list[dict[str, object]]:
    query = db.query(Auction).order_by(Auction.created_at.desc(), Auction.id.desc()).limit(limit)
    return [serialize_auction(auction) for auction in query.all()]


def list_parser_runs(db: Session, limit: int = 20) -> list[dict[str, object]]:
    query = db.query(SourceRun).order_by(SourceRun.id.desc()).limit(limit)
    return [serialize_source_run(run) for run in query.all()]


def list_top_cheapest_by_sotka(db: Session, limit: int = 10, region: str | None = None) -> list[dict[str, object]]:
    query = db.query(Auction).filter(Auction.price_per_sotka.is_not(None))
    if region:
        query = query.filter(Auction.region == region)

    query = query.order_by(Auction.price_per_sotka.asc(), Auction.id.asc()).limit(limit)
    return [serialize_auction(auction) for auction in query.all()]


def list_regions(db: Session) -> list[str]:
    rows = (
        db.query(Auction.region)
        .filter(Auction.region.is_not(None))
        .distinct()
        .order_by(Auction.region.asc())
        .all()
    )
    return [row[0] for row in rows]


def count_auctions(db: Session, region: str | None = None, status: str | None = None) -> int:
    query = db.query(func.count(Auction.id))
    if region:
        query = query.filter(Auction.region == region)
    if status:
        query = query.filter(Auction.status == status)
    return int(query.scalar() or 0)


def list_auctions_public(
    db: Session,
    limit: int = 50,
    region: str | None = None,
    status: str | None = None,
    order_by: str = "id",
) -> list[dict[str, object] | None]:
    return [
        auction_public_view(item)
        for item in list_auctions(db, limit=limit, region=region, status=status, order_by=order_by)
    ]


def list_recent_auctions_public(db: Session, limit: int = 10) -> list[dict[str, object] | None]:
    return [auction_public_view(item) for item in list_recent_auctions(db, limit=limit)]


def get_auction_card_public(db: Session, auction_id: int) -> dict[str, object] | None:
    return auction_card_public_view(get_auction_by_id(db, auction_id))


def list_top_cheapest_by_sotka_public(
    db: Session,
    limit: int = 10,
    region: str | None = None,
) -> list[dict[str, object] | None]:
    return [auction_public_view(item) for item in list_top_cheapest_by_sotka(db, limit=limit, region=region)]


def list_parser_runs_public(db: Session, limit: int = 20) -> list[dict[str, object] | None]:
    return [parser_run_public_view(item) for item in list_parser_runs(db, limit=limit)]
