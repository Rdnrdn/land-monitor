"""Alembic environment for land-monitor."""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from land_monitor.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
VERSION_TABLE_NAME = "alembic_version"
VERSION_COLUMN_NAME = "version_num"


def ensure_version_table_shape(connection: sa.Connection) -> None:
    """Keep Alembic's internal version table compatible with long revision ids.

    This repository uses descriptive revision strings such as
    ``20260408_add_notice_classification_flags`` which are longer than Alembic's
    default ``VARCHAR(32)`` for ``alembic_version.version_num``. When the first
    migration creates the table with the default size, later upgrades fail while
    updating the stored revision.
    """

    inspector = sa.inspect(connection)

    if VERSION_TABLE_NAME not in inspector.get_table_names():
        metadata = sa.MetaData()
        sa.Table(
            VERSION_TABLE_NAME,
            metadata,
            sa.Column(VERSION_COLUMN_NAME, sa.Text(), primary_key=True, nullable=False),
        )
        metadata.create_all(connection)
        return

    version_column = next(
        (column for column in inspector.get_columns(VERSION_TABLE_NAME) if column["name"] == VERSION_COLUMN_NAME),
        None,
    )
    if version_column is None:
        raise RuntimeError(f"{VERSION_TABLE_NAME}.{VERSION_COLUMN_NAME} column is missing.")

    current_length = getattr(version_column["type"], "length", None)
    if current_length is None:
        return

    quoted_table_name = connection.dialect.identifier_preparer.quote(VERSION_TABLE_NAME)
    quoted_column_name = connection.dialect.identifier_preparer.quote(VERSION_COLUMN_NAME)
    connection.execute(
        sa.text(
            f"ALTER TABLE {quoted_table_name} "
            f"ALTER COLUMN {quoted_column_name} TYPE TEXT"
        )
    )


def get_url() -> str:
    return os.getenv("DATABASE_URL", os.getenv("LAND_DB_URL", ""))


def run_migrations_offline() -> None:
    url = get_url()
    if not url:
        raise RuntimeError("DATABASE_URL or LAND_DB_URL must be set for alembic offline mode.")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    db_url = get_url()
    if db_url:
        configuration["sqlalchemy.url"] = db_url
    elif "sqlalchemy.url" not in configuration:
        raise RuntimeError("DATABASE_URL or LAND_DB_URL must be set for alembic.")

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        ensure_version_table_shape(connection)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
