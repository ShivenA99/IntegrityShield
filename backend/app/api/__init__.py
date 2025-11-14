from __future__ import annotations

from flask import Blueprint, Flask

from . import demo_routes, developer_routes, pipeline_routes, questions_routes, settings_routes


def register_blueprints(app: Flask) -> None:
    api_bp = Blueprint("api", __name__, url_prefix="/api")
    pipeline_routes.init_app(api_bp)
    questions_routes.init_app(api_bp)
    developer_routes.init_app(api_bp)
    settings_routes.init_app(api_bp)
    demo_routes.init_app(api_bp)
    # Defer files_routes import to avoid circular reference during module init
    from . import files_routes  # type: ignore
    files_routes.init_app(api_bp)
    app.register_blueprint(api_bp)
