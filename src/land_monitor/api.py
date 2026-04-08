"""FastAPI application for land-monitor public endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from land_monitor.db import SessionLocal
from land_monitor.crud import (
    list_lots_with_notice,
    list_user_lots,
    toggle_user_lot_favorite,
    update_user_lot_comment,
    update_user_lot_flags,
    update_user_lot_status,
)
from land_monitor.enums import UserLotStatus
from land_monitor.services.auctions import (
    get_auction_card_public,
    list_auctions_public,
    list_parser_runs_public,
    list_recent_auctions_public,
    list_regions,
    list_top_cheapest_by_sotka_public,
)
from land_monitor.services.user_lots import serialize_user_lot
from land_monitor.services.lot_presenter import build_lot_response

app = FastAPI(title="land-monitor API")
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/web/auctions", status_code=302)


@app.get("/auctions")
def auctions(
    limit: int = Query(50, ge=1, le=500),
    region: str | None = None,
    status: str | None = None,
    order_by: str = "id",
) -> list[dict[str, object] | None]:
    db = SessionLocal()
    try:
        return list_auctions_public(
            db,
            limit=limit,
            region=region,
            status=status,
            order_by=order_by,
        )
    finally:
        db.close()


@app.get("/auctions/recent")
def auctions_recent(limit: int = Query(10, ge=1, le=100)) -> list[dict[str, object] | None]:
    db = SessionLocal()
    try:
        return list_recent_auctions_public(db, limit=limit)
    finally:
        db.close()


@app.get("/auctions/cheapest")
def auctions_cheapest(
    limit: int = Query(10, ge=1, le=100),
    region: str | None = None,
) -> list[dict[str, object] | None]:
    db = SessionLocal()
    try:
        return list_top_cheapest_by_sotka_public(db, limit=limit, region=region)
    finally:
        db.close()


@app.get("/auctions/{auction_id}")
def auction_card(auction_id: int) -> dict[str, object] | None:
    db = SessionLocal()
    try:
        card = get_auction_card_public(db, auction_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Auction not found")
        return card
    finally:
        db.close()


@app.get("/parser-runs")
def parser_runs(limit: int = Query(20, ge=1, le=200)) -> list[dict[str, object] | None]:
    db = SessionLocal()
    try:
        return list_parser_runs_public(db, limit=limit)
    finally:
        db.close()


@app.get("/regions")
def regions() -> list[str]:
    db = SessionLocal()
    try:
        return list_regions(db)
    finally:
        db.close()


@app.get("/lots")
def lots(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict[str, object]]:
    db = SessionLocal()
    try:
        rows = list_lots_with_notice(db, limit=limit, offset=offset)
        return [build_lot_response(lot, notice) for lot, notice in rows]
    finally:
        db.close()


@app.get("/web/auctions")
def web_auctions(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    region: str | None = None,
    status: str | None = None,
    order_by: str = "id",
):
    db = SessionLocal()
    try:
        auctions = list_auctions_public(
            db,
            limit=limit,
            region=region or None,
            status=status or None,
            order_by=order_by,
        )
        return templates.TemplateResponse(
            request,
            "auctions.html",
            {
                "title": "Auctions",
                "heading": "Auctions",
                "auctions": auctions,
                "filters": {
                    "limit": limit,
                    "region": region or "",
                    "status": status or "",
                    "order_by": order_by,
                },
                "regions": list_regions(db),
                "view_name": "all",
            },
        )
    finally:
        db.close()


@app.get("/web/auctions/cheapest")
def web_auctions_cheapest(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    region: str | None = None,
):
    db = SessionLocal()
    try:
        auctions = list_top_cheapest_by_sotka_public(db, limit=limit, region=region or None)
        return templates.TemplateResponse(
            request,
            "auctions.html",
            {
                "title": "Cheapest Auctions",
                "heading": "Cheapest By Price Per Sotka",
                "auctions": auctions,
                "filters": {
                    "limit": limit,
                    "region": region or "",
                    "status": "",
                    "order_by": "price_per_sotka",
                },
                "regions": list_regions(db),
                "view_name": "cheapest",
            },
        )
    finally:
        db.close()


@app.get("/web/auctions/{auction_id}/view")
def web_auction_detail(request: Request, auction_id: int):
    db = SessionLocal()
    try:
        card = get_auction_card_public(db, auction_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Auction not found")
        return templates.TemplateResponse(
            request,
            "auction_detail.html",
            {
                "title": f"Auction #{auction_id}",
                "card": card,
            },
        )
    finally:
        db.close()


@app.get("/web/parser-runs")
def web_parser_runs(request: Request, limit: int = Query(20, ge=1, le=200)):
    db = SessionLocal()
    try:
        runs = list_parser_runs_public(db, limit=limit)
        return templates.TemplateResponse(
            request,
            "parser_runs.html",
            {
                "title": "Parser Runs",
                "runs": runs,
                "limit": limit,
            },
        )
    finally:
        db.close()


@app.get("/user-lots")
def user_lots(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)) -> list[dict[str, object]]:
    db = SessionLocal()
    try:
        lots = list_user_lots(db, limit=limit, offset=offset)
        return [serialize_user_lot(lot) for lot in lots]
    finally:
        db.close()


@app.patch("/user-lots/{user_lot_id}/status")
def user_lot_status(user_lot_id: int, payload: dict[str, str]) -> dict[str, object]:
    status_raw = payload.get("user_status")
    if status_raw is None:
        raise HTTPException(status_code=400, detail="user_status is required")
    try:
        status = UserLotStatus(status_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid user_status: {status_raw}") from exc

    db = SessionLocal()
    try:
        lot = update_user_lot_status(db, user_lot_id, status)
        if lot is None:
            raise HTTPException(status_code=404, detail="User lot not found")
        return serialize_user_lot(lot)
    finally:
        db.close()


@app.patch("/user-lots/{user_lot_id}/favorite")
def user_lot_favorite(user_lot_id: int, payload: dict[str, bool]) -> dict[str, object]:
    if "is_favorite" not in payload:
        raise HTTPException(status_code=400, detail="is_favorite is required")
    is_favorite = bool(payload["is_favorite"])
    db = SessionLocal()
    try:
        lot = toggle_user_lot_favorite(db, user_lot_id, is_favorite)
        if lot is None:
            raise HTTPException(status_code=404, detail="User lot not found")
        return serialize_user_lot(lot)
    finally:
        db.close()


@app.patch("/user-lots/{user_lot_id}/comment")
def user_lot_comment(user_lot_id: int, payload: dict[str, str | None]) -> dict[str, object]:
    comment = payload.get("comment")
    db = SessionLocal()
    try:
        lot = update_user_lot_comment(db, user_lot_id, comment)
        if lot is None:
            raise HTTPException(status_code=404, detail="User lot not found")
        return serialize_user_lot(lot)
    finally:
        db.close()


@app.patch("/user-lots/{user_lot_id}/flags")
def user_lot_flags(user_lot_id: int, payload: dict[str, bool | None]) -> dict[str, object]:
    db = SessionLocal()
    try:
        lot = update_user_lot_flags(
            db,
            user_lot_id,
            needs_inspection=payload.get("needs_inspection"),
            needs_legal_check=payload.get("needs_legal_check"),
            deposit_paid=payload.get("deposit_paid"),
        )
        if lot is None:
            raise HTTPException(status_code=404, detail="User lot not found")
        return serialize_user_lot(lot)
    finally:
        db.close()
