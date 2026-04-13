"""SQLAlchemy ORM models for land-monitor."""

from __future__ import annotations

from datetime import date, datetime
import uuid
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, Enum, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship
from sqlalchemy.sql.sqltypes import TIMESTAMP, Double

from land_monitor.enums import UserLotStatus

Base = declarative_base()


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(100), unique=True)
    base_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'active'"))
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))

    source_runs: Mapped[list["SourceRun"]] = relationship(back_populates="source")
    plots: Mapped[list["Plot"]] = relationship(back_populates="source")
    auctions: Mapped[list["Auction"]] = relationship(back_populates="source")
    listings: Mapped[list["Listing"]] = relationship(back_populates="source")
    price_history_entries: Mapped[list["PriceHistory"]] = relationship(back_populates="source")
    alert_rules: Mapped[list["AlertRule"]] = relationship(back_populates="source")


class SourceRun(Base):
    __tablename__ = "source_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'pending'"))
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))

    source: Mapped["Source"] = relationship(back_populates="source_runs")
    auctions: Mapped[list["Auction"]] = relationship(back_populates="source_run")
    listings: Mapped[list["Listing"]] = relationship(back_populates="source_run")


class Plot(Base):
    __tablename__ = "plots"
    __table_args__ = (
        Index(
            "idx_plots_cadastre_number_unique_not_null",
            "cadastre_number",
            unique=True,
            postgresql_where=text("cadastre_number IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    region: Mapped[str] = mapped_column(String(255), nullable=False)
    cadastre_number: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    area: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    area_sotka: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    latitude: Mapped[float | None] = mapped_column(Double)
    longitude: Mapped[float | None] = mapped_column(Double)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'new'"))
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))

    source: Mapped["Source | None"] = relationship(back_populates="plots")
    auctions: Mapped[list["Auction"]] = relationship(back_populates="plot")
    listings: Mapped[list["Listing"]] = relationship(back_populates="plot")
    alert_rules: Mapped[list["AlertRule"]] = relationship(back_populates="plot")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="plot")


class Auction(Base):
    __tablename__ = "auctions"
    __table_args__ = (
        Index("idx_auctions_source_external_id_unique", "source_id", "external_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    plot_id: Mapped[int | None] = mapped_column(ForeignKey("plots.id", ondelete="SET NULL"))
    source_run_id: Mapped[int | None] = mapped_column(ForeignKey("source_runs.id", ondelete="SET NULL"))
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'draft'"))
    region: Mapped[str | None] = mapped_column(String(255))
    start_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    end_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    start_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    final_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price_per_sotka: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(10), server_default=text("'RUB'"))
    raw_json: Mapped[dict | list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))

    source: Mapped["Source"] = relationship(back_populates="auctions")
    plot: Mapped["Plot | None"] = relationship(back_populates="auctions")
    source_run: Mapped["SourceRun | None"] = relationship(back_populates="auctions")
    price_history_entries: Mapped[list["PriceHistory"]] = relationship(back_populates="auction")
    alert_rules: Mapped[list["AlertRule"]] = relationship(back_populates="auction")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="auction")


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        Index("idx_listings_source_external_id_unique", "source_id", "external_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    plot_id: Mapped[int | None] = mapped_column(ForeignKey("plots.id", ondelete="SET NULL"))
    source_run_id: Mapped[int | None] = mapped_column(ForeignKey("source_runs.id", ondelete="SET NULL"))
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'active'"))
    region: Mapped[str | None] = mapped_column(String(255))
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price_per_sotka: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(10), server_default=text("'RUB'"))
    listing_url: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict | list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))

    source: Mapped["Source"] = relationship(back_populates="listings")
    plot: Mapped["Plot | None"] = relationship(back_populates="listings")
    source_run: Mapped["SourceRun | None"] = relationship(back_populates="listings")
    price_history_entries: Mapped[list["PriceHistory"]] = relationship(back_populates="listing")
    alert_rules: Mapped[list["AlertRule"]] = relationship(back_populates="listing")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="listing")


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        Index("uq_subjects_code", "code", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    okato: Mapped[str | None] = mapped_column(String(20))
    published: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    lots: Mapped[list["Lot"]] = relationship(back_populates="subject_ref")


class Region(Base):
    __tablename__ = "regions"
    __table_args__ = (
        Index("idx_regions_sort_order", "sort_order"),
        Index("uq_regions_slug", "slug", unique=True),
        Index("uq_regions_torgi_region_code", "torgi_region_code", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    torgi_region_code: Mapped[int] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))

    lots: Mapped[list["Lot"]] = relationship(back_populates="region_ref")


class Municipality(Base):
    __tablename__ = "municipalities"
    __table_args__ = (
        Index("idx_municipalities_region_sort_order", "region_id", "sort_order"),
        Index("uq_municipalities_region_normalized_name", "region_id", "normalized_name", unique=True),
        Index("uq_municipalities_region_slug", "region_id", "slug", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))

    region: Mapped["Region"] = relationship()
    lots: Mapped[list["Lot"]] = relationship(back_populates="municipality_ref")


class Lot(Base):
    __tablename__ = "lots"
    __table_args__ = (
        Index("idx_lots_region", "region"),
        Index("idx_lots_region_id", "region_id"),
        Index("idx_lots_municipality_id", "municipality_id"),
        Index("idx_lots_subject_id", "subject_id"),
        Index("idx_lots_notice_number", "notice_number"),
        Index("idx_lots_region_name", "region_name"),
        Index("idx_lots_price_min", "price_min"),
        Index("idx_lots_application_deadline", "application_deadline"),
        Index("idx_lots_application_end_at", "application_end_at"),
        Index("idx_lots_active_finished", "is_active", "is_finished"),
        Index("idx_lots_raw_data_gin", "raw_data", postgresql_using="gin"),
        Index("uq_lots_source_source_lot_id", "source", "source_lot_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'torgi'"))
    source_lot_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    notice_number: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("notices.notice_number", ondelete="SET NULL"),
    )

    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id", ondelete="SET NULL"),
        nullable=True,
    )
    region: Mapped[str | None] = mapped_column(Text)
    region_name: Mapped[str | None] = mapped_column(Text)
    source_torgi_region_code: Mapped[str | None] = mapped_column(Text)
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"),
        nullable=True,
    )
    subject_rf_code: Mapped[str | None] = mapped_column(Text)
    district: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    fias_guid: Mapped[str | None] = mapped_column(Text)

    cadastre_number: Mapped[str | None] = mapped_column(Text)
    area_m2: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    category: Mapped[str | None] = mapped_column(Text)
    permitted_use: Mapped[str | None] = mapped_column(Text)
    ownership_form_code: Mapped[str | None] = mapped_column(Text)
    ownership_form_name: Mapped[str | None] = mapped_column(Text)

    price_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price_fin: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    deposit_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency_code: Mapped[str | None] = mapped_column(Text)

    etp_code: Mapped[str | None] = mapped_column(Text)
    etp_name: Mapped[str | None] = mapped_column(Text)

    organizer_name: Mapped[str | None] = mapped_column(Text)
    organizer_inn: Mapped[str | None] = mapped_column(Text)
    organizer_kpp: Mapped[str | None] = mapped_column(Text)

    lot_status_external: Mapped[str | None] = mapped_column(Text)
    source_notice_bidd_type_code: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool | None] = mapped_column(Boolean)
    is_finished: Mapped[bool | None] = mapped_column(Boolean)

    application_start_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    application_deadline: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    application_end_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    auction_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    auction_start_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    source_created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    lotcard_enriched_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    price_bucket: Mapped[str | None] = mapped_column(Text)
    days_to_deadline: Mapped[int | None] = mapped_column()
    is_price_null: Mapped[bool | None] = mapped_column(Boolean)
    is_etp_empty: Mapped[bool | None] = mapped_column(Boolean)
    is_without_etp: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[int | None] = mapped_column()
    segment: Mapped[str | None] = mapped_column(Text)
    municipality_name: Mapped[str | None] = mapped_column(Text)
    municipality_id: Mapped[int | None] = mapped_column(
        ForeignKey("municipalities.id", ondelete="SET NULL"),
        nullable=True,
    )
    settlement_name: Mapped[str | None] = mapped_column(Text)
    municipality_fias_guid: Mapped[str | None] = mapped_column(Text)
    settlement_fias_guid: Mapped[str | None] = mapped_column(Text)

    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    region_ref: Mapped["Region | None"] = relationship(back_populates="lots")
    subject_ref: Mapped["Subject | None"] = relationship(back_populates="lots")
    municipality_ref: Mapped["Municipality | None"] = relationship(back_populates="lots")


class Notice(Base):
    __tablename__ = "notices"
    __table_args__ = (
        Index("idx_notices_notice_number", "notice_number", unique=True),
        Index("idx_notices_auction_site_domain", "auction_site_domain"),
        Index("idx_notices_raw_data_gin", "raw_data", postgresql_using="gin"),
        Index(
            "idx_notices_opendata_publish_sort",
            "publish_date",
            "fetched_at",
            "notice_number",
            postgresql_where=text("raw_data ? 'opendata'"),
        ),
    )

    notice_number: Mapped[str] = mapped_column(Text, primary_key=True)
    notice_status: Mapped[str | None] = mapped_column(Text)
    publish_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    create_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    update_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    bidd_type_code: Mapped[str | None] = mapped_column(Text)
    bidd_form_code: Mapped[str | None] = mapped_column(Text)
    bidder_org_name: Mapped[str | None] = mapped_column(Text)
    right_holder_name: Mapped[str | None] = mapped_column(Text)
    auction_site_url: Mapped[str | None] = mapped_column(Text)
    auction_site_domain: Mapped[str | None] = mapped_column(Text)
    application_portal_url: Mapped[str | None] = mapped_column(Text)
    application_portal_domain: Mapped[str | None] = mapped_column(Text)
    is_pre_auction: Mapped[bool | None] = mapped_column(Boolean)
    is_39_18: Mapped[bool | None] = mapped_column(Boolean)
    auction_is_electronic: Mapped[bool | None] = mapped_column(Boolean)
    detected_site_type: Mapped[str | None] = mapped_column(Text)
    detected_platform_code: Mapped[str | None] = mapped_column(Text)
    is_offline: Mapped[bool | None] = mapped_column(Boolean)
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    fetched_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class OpendataNoticeVersion(Base):
    __tablename__ = "opendata_notice_versions"
    __table_args__ = (
        UniqueConstraint(
            "reg_num",
            "document_type",
            "publish_date",
            "href",
            name="uq_opendata_notice_versions_version",
        ),
        Index("idx_opendata_notice_versions_status", "status"),
        Index("idx_opendata_notice_versions_reg_num", "reg_num"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reg_num: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str] = mapped_column(Text, nullable=False)
    publish_date: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    source_date: Mapped[date] = mapped_column(Date, nullable=False)
    href: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    downloaded_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )


class UserLot(Base):
    __tablename__ = "user_lots"
    __table_args__ = (
        Index("idx_user_lots_user_status", "user_status"),
        Index("idx_user_lots_is_favorite", "is_favorite"),
        Index("uq_user_lots_lot_id", "lot_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lot_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lots.id", ondelete="CASCADE"), nullable=False)
    user_status: Mapped[UserLotStatus] = mapped_column(
        Enum(UserLotStatus, name="user_lot_status", native_enum=True),
        nullable=False,
        server_default=text("'NEW'"),
    )
    is_favorite: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=text("false"),
    )
    needs_inspection: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=text("false"),
    )
    needs_legal_check: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=text("false"),
    )
    deposit_paid: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=text("false"),
    )
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        CheckConstraint("auction_id IS NOT NULL OR listing_id IS NOT NULL", name="price_history_parent_check"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    auction_id: Mapped[int | None] = mapped_column(ForeignKey("auctions.id", ondelete="CASCADE"))
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"))
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(10), server_default=text("'RUB'"))
    recorded_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))

    source: Mapped["Source | None"] = relationship(back_populates="price_history_entries")
    auction: Mapped["Auction | None"] = relationship(back_populates="price_history_entries")
    listing: Mapped["Listing | None"] = relationship(back_populates="price_history_entries")


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint(
            "plot_id IS NOT NULL OR listing_id IS NOT NULL OR auction_id IS NOT NULL",
            name="alert_rules_target_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    plot_id: Mapped[int | None] = mapped_column(ForeignKey("plots.id", ondelete="CASCADE"))
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"))
    auction_id: Mapped[int | None] = mapped_column(ForeignKey("auctions.id", ondelete="CASCADE"))
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False)
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'active'"))
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))

    source: Mapped["Source | None"] = relationship(back_populates="alert_rules")
    plot: Mapped["Plot | None"] = relationship(back_populates="alert_rules")
    listing: Mapped["Listing | None"] = relationship(back_populates="alert_rules")
    auction: Mapped["Auction | None"] = relationship(back_populates="alert_rules")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="alert_rule")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_rule_id: Mapped[int] = mapped_column(ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False)
    plot_id: Mapped[int | None] = mapped_column(ForeignKey("plots.id", ondelete="SET NULL"))
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id", ondelete="SET NULL"))
    auction_id: Mapped[int | None] = mapped_column(ForeignKey("auctions.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'new'"))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=text("NOW()"))

    alert_rule: Mapped["AlertRule"] = relationship(back_populates="alerts")
    plot: Mapped["Plot | None"] = relationship(back_populates="alerts")
    listing: Mapped["Listing | None"] = relationship(back_populates="alerts")
    auction: Mapped["Auction | None"] = relationship(back_populates="alerts")
