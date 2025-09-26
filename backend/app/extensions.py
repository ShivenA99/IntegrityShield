from __future__ import annotations

from flask_cors import CORS
from flask_migrate import Migrate
from flask_sock import Sock
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
migrate = Migrate()
sock = Sock()
cors = CORS()


def init_extensions(app) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}})
    sock.init_app(app)
