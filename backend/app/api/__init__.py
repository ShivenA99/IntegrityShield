from __future__ import annotations

from flask import Blueprint, Flask

from . import developer_routes, pipeline_routes, questions_routes, settings_routes


api_bp = Blueprint("api", __name__, url_prefix="/api")


def register_blueprints(app: Flask) -> None:
    pipeline_routes.init_app(api_bp)
    questions_routes.init_app(api_bp)
    developer_routes.init_app(api_bp)
    settings_routes.init_app(api_bp)
    # Defer files_routes import to avoid circular reference during module init
    from . import files_routes  # type: ignore
    files_routes.init_app(api_bp)
    app.register_blueprint(api_bp)
