"""Refactor lots and user_lots schema.

Revision ID: 20260407_lots_user_lots_refactor
Revises:
Create Date: 2026-04-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260407_lots_user_lots_refactor"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(inspector: sa.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _column_names(inspector: sa.Inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_lot_status') THEN
                CREATE TYPE user_lot_status AS ENUM (
                    'NEW','REVIEW','PLAN','APPLIED','BIDDING','WON','LOST','SKIPPED','ARCHIVE'
                );
            END IF;
        END $$;
        """
    )

    if not _table_exists(inspector, "lots"):
        op.create_table(
            "lots",
            sa.Column("id", sa.BigInteger, primary_key=True),
            sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'torgi'")),
            sa.Column("source_lot_id", sa.Text(), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column("title", sa.Text()),
            sa.Column("description", sa.Text()),
            sa.Column("region", sa.Text()),
            sa.Column("district", sa.Text()),
            sa.Column("address", sa.Text()),
            sa.Column("fias_guid", sa.Text()),
            sa.Column("cadastre_number", sa.Text()),
            sa.Column("area_m2", sa.Numeric()),
            sa.Column("category", sa.Text()),
            sa.Column("permitted_use", sa.Text()),
            sa.Column("price_min", sa.Numeric()),
            sa.Column("price_fin", sa.Numeric()),
            sa.Column("deposit_amount", sa.Numeric()),
            sa.Column("currency_code", sa.Text()),
            sa.Column("etp_code", sa.Text()),
            sa.Column("etp_name", sa.Text()),
            sa.Column("organizer_name", sa.Text()),
            sa.Column("organizer_inn", sa.Text()),
            sa.Column("organizer_kpp", sa.Text()),
            sa.Column("lot_status_external", sa.Text()),
            sa.Column("is_active", sa.Boolean()),
            sa.Column("is_finished", sa.Boolean()),
            sa.Column("application_start_date", sa.TIMESTAMP(timezone=True)),
            sa.Column("application_deadline", sa.TIMESTAMP(timezone=True)),
            sa.Column("auction_date", sa.TIMESTAMP(timezone=True)),
            sa.Column("source_created_at", sa.TIMESTAMP(timezone=True)),
            sa.Column("source_updated_at", sa.TIMESTAMP(timezone=True)),
            sa.Column("price_bucket", sa.Text()),
            sa.Column("days_to_deadline", sa.Integer()),
            sa.Column("is_price_null", sa.Boolean()),
            sa.Column("is_etp_empty", sa.Boolean()),
            sa.Column("score", sa.Integer()),
            sa.Column("segment", sa.Text()),
            sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
            sa.UniqueConstraint("source", "source_lot_id", name="uq_lots_source_source_lot_id"),
        )
        op.create_index("idx_lots_region", "lots", ["region"])
        op.create_index("idx_lots_price_min", "lots", ["price_min"])
        op.create_index("idx_lots_application_deadline", "lots", ["application_deadline"])
        op.create_index("idx_lots_active_finished", "lots", ["is_active", "is_finished"])
        op.create_index("idx_lots_raw_data_gin", "lots", ["raw_data"], postgresql_using="gin")

    if _table_exists(inspector, "user_lots"):
        columns = _column_names(inspector, "user_lots")

        if "lot_id" not in columns:
            op.add_column("user_lots", sa.Column("lot_id", sa.BigInteger()))

        if "source_lot_id" in columns:
            op.execute(
                """
                INSERT INTO lots (
                    source, source_lot_id, source_url, title, region, district,
                    cadastre_number, area_m2, price_min, deposit_amount, etp_code,
                    lot_status_external, application_deadline, auction_date, raw_data,
                    created_at, updated_at
                )
                SELECT DISTINCT
                    'torgi',
                    source_lot_id,
                    COALESCE(source_url, ''),
                    title,
                    region,
                    district,
                    cadastre_number,
                    area_m2,
                    price_min,
                    deposit_amount,
                    etp_code,
                    lot_status_external,
                    application_deadline,
                    auction_date,
                    '{}'::jsonb,
                    NOW(),
                    NOW()
                FROM user_lots
                WHERE source_lot_id IS NOT NULL
                ON CONFLICT (source, source_lot_id) DO NOTHING;
                """
            )
            op.execute(
                """
                UPDATE user_lots u
                SET lot_id = l.id
                FROM lots l
                WHERE l.source = 'torgi' AND l.source_lot_id = u.source_lot_id;
                """
            )

        if "user_status" in columns:
            op.execute(
                "ALTER TABLE user_lots ALTER COLUMN user_status TYPE user_lot_status USING user_status::user_lot_status"
            )

        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_user_lots_lot_id'
                ) THEN
                    ALTER TABLE user_lots ADD CONSTRAINT uq_user_lots_lot_id UNIQUE (lot_id);
                END IF;
            END $$;
            """
        )

        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_user_lots_lot_id'
                ) THEN
                    ALTER TABLE user_lots
                        ADD CONSTRAINT fk_user_lots_lot_id
                        FOREIGN KEY (lot_id) REFERENCES lots(id) ON DELETE CASCADE;
                END IF;
            END $$;
            """
        )

        if "id" in columns:
            id_type = next(col["type"] for col in inspector.get_columns("user_lots") if col["name"] == "id")
            if not isinstance(id_type, postgresql.UUID):
                op.execute("ALTER TABLE user_lots ADD COLUMN IF NOT EXISTS id_uuid UUID DEFAULT gen_random_uuid()")
                op.execute("UPDATE user_lots SET id_uuid = gen_random_uuid() WHERE id_uuid IS NULL")
                op.execute("ALTER TABLE user_lots DROP CONSTRAINT IF EXISTS user_lots_pkey")
                op.execute("ALTER TABLE user_lots DROP COLUMN id")
                op.execute("ALTER TABLE user_lots RENAME COLUMN id_uuid TO id")
                op.execute("ALTER TABLE user_lots ADD PRIMARY KEY (id)")

        if "source_lot_id" in columns:
            drop_cols = [
                "source_lot_id",
                "source_url",
                "title",
                "region",
                "district",
                "cadastre_number",
                "area_m2",
                "price_min",
                "deposit_amount",
                "etp_code",
                "lot_status_external",
                "application_deadline",
                "auction_date",
            ]
            for col in drop_cols:
                op.execute(f"ALTER TABLE user_lots DROP COLUMN IF EXISTS {col}")

        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM user_lots WHERE lot_id IS NULL) THEN
                    ALTER TABLE user_lots ALTER COLUMN lot_id SET NOT NULL;
                END IF;
            END $$;
            """
        )
    else:
        op.create_table(
            "user_lots",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("lot_id", sa.BigInteger, sa.ForeignKey("lots.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "user_status",
                postgresql.ENUM(
                    "NEW",
                    "REVIEW",
                    "PLAN",
                    "APPLIED",
                    "BIDDING",
                    "WON",
                    "LOST",
                    "SKIPPED",
                    "ARCHIVE",
                    name="user_lot_status",
                    create_type=False,
                ),
                nullable=False,
                server_default=sa.text("'NEW'"),
            ),
            sa.Column("is_favorite", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("needs_inspection", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("needs_legal_check", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("deposit_paid", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("comment", sa.Text()),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
            sa.UniqueConstraint("lot_id", name="uq_user_lots_lot_id"),
        )
        op.create_index("idx_user_lots_user_status", "user_lots", ["user_status"])
        op.create_index("idx_user_lots_is_favorite", "user_lots", ["is_favorite"])


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_lots")
    op.execute("DROP TABLE IF EXISTS lots")
    op.execute("DROP TYPE IF EXISTS user_lot_status")
