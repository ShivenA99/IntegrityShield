"""Encryption utilities for API keys and sensitive data."""

from __future__ import annotations

import base64
import os
from typing import Optional

from cryptography.fernet import Fernet
from flask import current_app


def get_encryption_key() -> bytes:
    """Get or generate encryption key from app config."""
    secret_key = current_app.config.get("SECRET_KEY", "dev-secret-key")
    # Derive a Fernet key from the secret key
    # In production, use a proper key derivation function
    key_material = secret_key.encode()[:32].ljust(32, b"0")
    return base64.urlsafe_b64encode(key_material)


def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key for storage."""
    key = get_encryption_key()
    f = Fernet(key)
    encrypted = f.encrypt(api_key.encode())
    return base64.urlsafe_b64encode(encrypted).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key from storage."""
    key = get_encryption_key()
    f = Fernet(key)
    encrypted_bytes = base64.urlsafe_b64decode(encrypted_key.encode())
    decrypted = f.decrypt(encrypted_bytes)
    return decrypted.decode()

