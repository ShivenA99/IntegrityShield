from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import generate_password_hash, check_password_hash

from ..extensions import db
from .pipeline import TimestampMixin


class User(db.Model, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        db.String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(db.String(255), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(db.String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(db.String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(db.Boolean, default=True, nullable=False)

    api_keys: Mapped[list["UserAPIKey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    def set_password(self, password: str) -> None:
        """Hash and set the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check if the provided password matches the user's password."""
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict[str, Any]:
        """Convert user to dictionary (excluding sensitive data)."""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UserAPIKey(db.Model, TimestampMixin):
    __tablename__ = "user_api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(db.String(32), nullable=False)  # openai, gemini, grok, anthropic
    encrypted_key: Mapped[str] = mapped_column(db.Text, nullable=False)  # Encrypted API key
    is_active: Mapped[bool] = mapped_column(db.Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="api_keys")

    __table_args__ = (db.UniqueConstraint("user_id", "provider", name="uq_user_provider"),)

    def to_dict(self) -> dict[str, Any]:
        """Convert API key to dictionary (excluding the actual key)."""
        return {
            "id": self.id,
            "provider": self.provider,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

