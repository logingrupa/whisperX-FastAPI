"""This module provides database connection and session management.

On import, registers a SQLAlchemy event listener that enforces
SQLite foreign-key constraints on every new connection (SCHEMA-05),
and asserts at module load that the pragma actually took effect — fail
loudly per tiger-style (CONTEXT §69).
"""

from collections.abc import Callable, Generator
from functools import wraps
from sqlite3 import Connection as SQLite3Connection
from typing import Any

from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Config
from app.core.logging import logger

# Load environment variables from .env
load_dotenv()

# Create engine and session
DB_URL = Config.DB_URL
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})


@event.listens_for(Engine, "connect")
def _enforce_sqlite_foreign_keys(
    dbapi_connection: Any,
    connection_record: Any,
) -> None:
    """Enforce SQLite foreign-key constraints on every new connection.

    SQLite ships with FK enforcement OFF by default. The listener turns it
    ON for every connection the engine creates. Non-SQLite drivers are
    skipped early (no nested ifs).

    Args:
        dbapi_connection: Raw DB-API connection object.
        connection_record: SQLAlchemy connection pool record.
    """
    # Guard: only act on SQLite connections.
    if not isinstance(dbapi_connection, SQLite3Connection):
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
    finally:
        cursor.close()
    logger.debug("PRAGMA foreign_keys=ON applied to new SQLite connection")


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Tiger-style: fail loudly at module load if FK enforcement isn't actually on.
# Per CONTEXT §69 (locked code quality bar).
with engine.connect() as _verify_conn:
    _fk_on = _verify_conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
    assert _fk_on == 1, (
        f"PRAGMA foreign_keys MUST be ON, got {_fk_on}; check listener registration"
    )


def get_db_session() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def handle_database_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    """Handle database errors and raise HTTP exceptions."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except SQLAlchemyError as e:
            error_message = f"Database error: {str(e)}"
            raise HTTPException(status_code=500, detail=error_message)

    return wrapper
