import os
import logging

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
from sqlalchemy import MetaData
from flask_cors import CORS

# Load env vars from a .env file if present (useful in local dev)
load_dotenv()

_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=_convention)

# Pass the metadata with conventions to SQLAlchemy so Alembic picks it up
db = SQLAlchemy(metadata=metadata)
migrate = Migrate()

def create_app() -> Flask:
    """Application factory."""
    # ------------------------------------------------------------------
    # Logging – ensure we have at least basic configuration so Blueprints
    # can emit useful diagnostics.
    # ------------------------------------------------------------------
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)8s | %(name)s:%(lineno)d - %(message)s",
    )

    app = Flask(__name__)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://localhost/ftai",
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------
    db.init_app(app)
    migrate.init_app(app, db)
    # Allow local Vite dev server (5173) to reach the API
    CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"], supports_credentials=True)

    # ------------------------------------------------------------------
    # Blueprints
    # ------------------------------------------------------------------
    from .routes.assessments import assessments_bp

    app.register_blueprint(assessments_bp, url_prefix="/api/assessments")

    return app 