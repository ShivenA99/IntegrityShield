from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request

from ..services.config.settings_manager import SettingsManager

bp = Blueprint("settings", __name__, url_prefix="/settings")
_settings_manager = SettingsManager()


def init_app(api_bp: Blueprint) -> None:
    api_bp.register_blueprint(bp)


@bp.get("/")
def get_settings():
    settings = _settings_manager.load()
    return jsonify(settings)


@bp.put("/")
def update_settings():
    payload = request.get_json(silent=True) or {}
    if "suffix_spacing_bias" not in payload:
        return (
            jsonify({"error": "suffix_spacing_bias is required"}),
            HTTPStatus.BAD_REQUEST,
        )

    try:
        bias_value = float(payload.get("suffix_spacing_bias"))
    except (TypeError, ValueError):
        return (
            jsonify({"error": "suffix_spacing_bias must be numeric"}),
            HTTPStatus.BAD_REQUEST,
        )

    if not -5000.0 <= bias_value <= 5000.0:
        return (
            jsonify({"error": "suffix_spacing_bias must be between -5000 and 5000"}),
            HTTPStatus.BAD_REQUEST,
        )

    settings = _settings_manager.update({"suffix_spacing_bias": bias_value})
    return jsonify(settings)
