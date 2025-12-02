"""Authentication utilities."""

from __future__ import annotations

import jwt
from datetime import datetime, timedelta
from typing import Optional

from flask import current_app, request
from ..models.user import User


def generate_token(user: User) -> str:
    """Generate a JWT token for a user."""
    payload = {
        "user_id": user.id,
        "email": user.email,
        "exp": datetime.utcnow() + timedelta(days=30),  # Token expires in 30 days
        "iat": datetime.utcnow(),
    }
    secret_key = current_app.config.get("SECRET_KEY", "dev-secret-key")
    return jwt.encode(payload, secret_key, algorithm="HS256")


def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token."""
    try:
        secret_key = current_app.config.get("SECRET_KEY", "dev-secret-key")
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user() -> Optional[User]:
    """Get the current authenticated user from the request."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    try:
        # Expect "Bearer <token>"
        token = auth_header.split(" ")[1]
        payload = verify_token(token)
        if not payload:
            return None

        user_id = payload.get("user_id")
        if not user_id:
            return None

        return User.query.get(user_id)
    except (IndexError, AttributeError):
        return None


def require_auth(func):
    """Decorator to require authentication for a route."""
    from functools import wraps
    from flask import jsonify

    @wraps(func)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401
        if not user.is_active:
            return jsonify({"error": "Account is inactive"}), 403
        return func(*args, **kwargs, current_user=user)

    return wrapper

