from __future__ import annotations

import logging

from flask import current_app
from flask_migrate import upgrade
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError
from alembic.util.exc import CommandError

from ..extensions import db

logger = logging.getLogger(__name__)


def ensure_database_schema() -> None:
    """Apply pending migrations (or create tables as a fallback).

    This keeps developer environments synchronized without requiring
    a separate migration command before using new classroom features.
    """
    app = current_app
    if not app.config.get("AUTO_APPLY_DB_MIGRATIONS", True):
        logger.debug("AUTO_APPLY_DB_MIGRATIONS disabled; skipping automatic upgrade.")
        return

    database_uri: str = app.config.get("SQLALCHEMY_DATABASE_URI", "")

    # In-memory SQLite databases need a create_all because Alembic opens a new connection.
    if database_uri.startswith("sqlite:///:memory:"):
        _create_all_tables()
        return

    # Apply migrations; fallback to metadata bootstrap if anything fails early in dev setups.
    try:
        upgrade()
    except (OperationalError, CommandError) as exc:
        logger.warning(
            "Automatic migration failed (%s); attempting metadata bootstrap via create_all.",
            exc,
        )
        _create_all_tables()
    except Exception:  # pragma: no cover - defensive guard for unexpected failures
        if not _table_exists("answer_sheet_runs"):
            logger.exception(
                "Automatic migration failed unexpectedly; attempting metadata bootstrap via create_all."
            )
            _create_all_tables()
        else:
            logger.exception("Automatic migration failed; schema may be outdated.")


def _create_all_tables() -> None:
    """Ensure tables exist when migrations are unavailable."""
    from .. import models  # noqa: WPS433 - imported for side effects

    db.create_all()


def _table_exists(name: str) -> bool:
    inspector = inspect(db.engine)
    return name in inspector.get_table_names()
