from __future__ import annotations

import hashlib
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
    email: Mapped[Optional[str]] = mapped_column(db.String(255), nullable=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(db.String(255), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(db.String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(db.Boolean, default=True, nullable=False)

    # OpenAI key authentication fields
    openai_key_hash: Mapped[Optional[str]] = mapped_column(db.String(64), unique=True, nullable=True, index=True)
    encrypted_openai_key: Mapped[Optional[str]] = mapped_column(db.Text, nullable=True)

    api_keys: Mapped[list["UserAPIKey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    def set_password(self, password: str) -> None:
        """Hash and set the user's password."""
        # Use pbkdf2:sha256 for Python 3.9 compatibility (scrypt requires 3.10+)
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password: str) -> bool:
        """Check if the provided password matches the user's password."""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def hash_openai_key(api_key: str) -> str:
        """Generate SHA256 hash of OpenAI key for unique identification."""
        return hashlib.sha256(api_key.encode('utf-8')).hexdigest()

    def set_openai_key(self, api_key: str) -> None:
        """Encrypt and store OpenAI key, set hash as identifier."""
        from ..utils.encryption import encrypt_api_key
        self.openai_key_hash = self.hash_openai_key(api_key)
        self.encrypted_openai_key = encrypt_api_key(api_key)

    def get_openai_key(self) -> Optional[str]:
        """Decrypt and return OpenAI key."""
        if not self.encrypted_openai_key:
            return None
        from ..utils.encryption import decrypt_api_key
        return decrypt_api_key(self.encrypted_openai_key)

    def to_dict(self) -> dict[str, Any]:
        """Convert user to dictionary (excluding sensitive data)."""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "is_active": self.is_active,
            "has_openai_key": bool(self.encrypted_openai_key),
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

