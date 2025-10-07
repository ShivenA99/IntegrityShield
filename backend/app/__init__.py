from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv(Path.cwd() / ".env")

from .config import get_config
from .extensions import db, init_extensions
from .utils.json import ORJSONProvider
from .utils.logging import configure_logging


def create_app(config_name: str | None = None) -> Flask:
    config_class = get_config(config_name)
    app = Flask(__name__)
    app.config.from_object(config_class)

    app.json = ORJSONProvider(app)

    configure_logging(app)
    init_extensions(app)

    from .api import register_blueprints
    register_blueprints(app)

    register_error_handlers(app)
    register_shellcontext(app)

    return app


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def handle_not_found(error):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def handle_server_error(error):
        app.logger.exception("Unhandled server error")
        return jsonify({"error": "Internal server error"}), 500


def register_shellcontext(app: Flask) -> None:
    @app.shell_context_processor
    def shell_context():
        from . import models  # noqa: F401

        return {"db": db}
