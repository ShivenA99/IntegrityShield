from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _parse_cors_origins() -> str | list[str]:
    default = (
        "http://localhost:3000,http://localhost:5173,http://localhost:5175,"
        "http://127.0.0.1:3000,http://127.0.0.1:5173,http://127.0.0.1:5175"
    )
    raw = os.getenv("FAIRTESTAI_CORS_ORIGINS", default)
    if raw.strip() == "*":
        return "*"
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or "*"


class BaseConfig:
    SECRET_KEY = os.getenv("FAIRTESTAI_SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "FAIRTESTAI_DATABASE_URL",
        f"sqlite:///{(Path.cwd() / 'data' / 'fairtestai.db').resolve()}",
    )
    SQLALCHEMY_ENGINE_OPTIONS: dict[str, Any] = {"pool_pre_ping": True}
    if SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {
            "check_same_thread": False,
            "timeout": float(os.getenv("FAIRTESTAI_SQLITE_TIMEOUT_SECONDS", "30")),
        }
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200 MB uploads
    CORS_ORIGINS = "*"
    PIPELINE_STORAGE_ROOT = Path(
        os.getenv("FAIRTESTAI_PIPELINE_ROOT", Path.cwd() / "data" / "pipeline_runs")
    )
    LOG_LEVEL = os.getenv("FAIRTESTAI_LOG_LEVEL", "INFO")
    FILE_STORAGE_BUCKET = os.getenv("FAIRTESTAI_FILE_STORAGE_BUCKET")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    GOOGLE_AI_KEY = os.getenv("GOOGLE_AI_KEY")
    ENABLE_DEVELOPER_TOOLS = (
        os.getenv("FAIRTESTAI_ENABLE_DEV_TOOLS", "true").lower() == "true"
    )
    AUTO_APPLY_DB_MIGRATIONS = (
        os.getenv("FAIRTESTAI_AUTO_APPLY_MIGRATIONS", "true").lower() == "true"
    )
    PIPELINE_DEFAULT_MODELS = os.getenv(
        "FAIRTESTAI_DEFAULT_MODELS", "gpt-4o-mini,claude-3-5-sonnet,gemini-1.5-pro"
    ).split(",")
    PIPELINE_DEFAULT_METHODS = os.getenv(
        "FAIRTESTAI_DEFAULT_METHODS",
        "latex_dual_layer,pymupdf_overlay",
    ).split(",")
    ANSWER_SHEET_DEFAULTS: dict[str, Any] = {
        "total_students": int(os.getenv("FAIRTESTAI_ANSWER_SHEET_TOTAL", "100")),
        "cheating_rate": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_CHEATING_RATE", "0.35")),
        "cheating_breakdown": {
            "llm": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_CHEATER_LLM", "0.6")),
            "peer": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_CHEATER_PEER", "0.4")),
        },
        "copy_profile": {
            "full_copy_probability": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_FULL_COPY_PROB", "0.45")),
            "partial_copy_min": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_PARTIAL_MIN", "0.4")),
            "partial_copy_max": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_PARTIAL_MAX", "0.75")),
        },
        "paraphrase_probability": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_PARAPHRASE_PROB", "0.65")),
        "score_distribution": {
            "fair": {
                "mean": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_FAIR_MEAN", "75")),
                "stddev": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_FAIR_STD", "10")),
                "min": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_FAIR_MIN", "45")),
                "max": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_FAIR_MAX", "95")),
            },
            "cheating_llm": {
                "mean": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_LLM_MEAN", "92")),
                "stddev": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_LLM_STD", "4")),
                "min": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_LLM_MIN", "80")),
                "max": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_LLM_MAX", "100")),
            },
            "cheating_peer": {
                "mean": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_PEER_MEAN", "72")),
                "stddev": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_PEER_STD", "8")),
                "min": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_PEER_MIN", "40")),
                "max": float(os.getenv("FAIRTESTAI_ANSWER_SHEET_PEER_MAX", "92")),
            },
        },
        "write_parquet": os.getenv("FAIRTESTAI_ANSWER_SHEET_WRITE_PARQUET", "false").lower() == "true",
        "random_seed": os.getenv("FAIRTESTAI_ANSWER_SHEET_SEED"),
        "subjective_llm": {
            "enabled": os.getenv("FAIRTESTAI_SUBJECTIVE_LLM_ENABLED", "true").lower() == "true",
            "model": os.getenv("FAIRTESTAI_SUBJECTIVE_LLM_MODEL", "gpt-4o-mini"),
            "temperature": float(os.getenv("FAIRTESTAI_SUBJECTIVE_LLM_TEMPERATURE", "0.2")),
            "max_tokens": int(os.getenv("FAIRTESTAI_SUBJECTIVE_LLM_MAX_TOKENS", "300")),
            "api_key": os.getenv("FAIRTESTAI_SUBJECTIVE_LLM_API_KEY"),
            "timeout_seconds": float(os.getenv("FAIRTESTAI_SUBJECTIVE_LLM_TIMEOUT", "30")),
        },
    }
    WEBSOCKET_URL_PREFIX = "/ws"
    POST_FUSER_MODEL = os.getenv("POST_FUSER_MODEL", "gpt-5")
    DEMO_ASSETS_PATH = os.getenv("FAIRTESTAI_DEMO_ASSETS_PATH")
    MANUAL_INPUT_DIR = Path(
        os.getenv(
            "FAIRTESTAI_MANUAL_INPUT_DIR",
            Path.cwd() / "data" / "manual_inputs" / "current",
        )
    )


class TestConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    PIPELINE_STORAGE_ROOT = Path("/tmp/fairtestai-test")
    LOG_LEVEL = "DEBUG"


class DevConfig(BaseConfig):
    DEBUG = True
    LOG_LEVEL = "DEBUG"


config_by_name = {
    "development": DevConfig,
    "testing": TestConfig,
    "production": BaseConfig,
}


def get_config(config_name: str | None = None):
    if not config_name:
        config_name = os.getenv("FAIRTESTAI_ENV", "development")
    return config_by_name.get(config_name.lower(), BaseConfig)
