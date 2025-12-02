from __future__ import annotations

import os
import sqlite3

from flask_cors import CORS
from flask_migrate import Migrate
from flask_sock import Sock
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine


db = SQLAlchemy()
migrate = Migrate()
sock = Sock()
cors = CORS()


def init_extensions(app) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}})
    sock.init_app(app)


@event.listens_for(Engine, "connect")
def configure_sqlite_connection(dbapi_connection, connection_record) -> None:
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return

    busy_timeout_seconds = float(os.getenv("FAIRTESTAI_SQLITE_TIMEOUT_SECONDS", "30"))
    busy_timeout_ms = int(max(busy_timeout_seconds, 0) * 1000)

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.fetchall()
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.fetchall()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.fetchall()
        cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms};")
    finally:
        cursor.close()
