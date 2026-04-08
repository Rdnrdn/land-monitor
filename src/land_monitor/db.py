"""Database utilities for land-monitor."""

from __future__ import annotations

import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()


def _get_database_url() -> str:
    host = os.getenv("LAND_DB_HOST", "localhost")
    port = os.getenv("LAND_DB_PORT", "5432")
    name = os.getenv("LAND_DB_NAME", "land_monitor")
    user = os.getenv("LAND_DB_USER", "land_user")
    password = os.getenv("LAND_DB_PASSWORD", "")

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


DATABASE_URL = _get_database_url()

engine: Engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and close it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_connection() -> tuple[bool, str]:
    """Check that the database is reachable and accepting queries."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, "Database connection successful."
    except Exception as exc:  # pragma: no cover - useful for operational feedback
        return False, f"Database connection failed: {exc}"
