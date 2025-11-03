from __future__ import annotations

import os
from pathlib import Path


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
    PIPELINE_DEFAULT_MODELS = os.getenv(
        "FAIRTESTAI_DEFAULT_MODELS", "gpt-4o-mini,claude-3-5-sonnet,gemini-1.5-pro"
    ).split(",")
    PIPELINE_DEFAULT_METHODS = os.getenv(
        "FAIRTESTAI_DEFAULT_METHODS",
        "content_stream_overlay,pymupdf_overlay",
    ).split(",")
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
