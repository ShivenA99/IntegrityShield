"""Authentication routes."""

from __future__ import annotations

import re
from http import HTTPStatus
from typing import Any

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models.user import User, UserAPIKey
from ..utils.auth import generate_token, require_auth, get_current_user
from ..utils.encryption import encrypt_api_key, decrypt_api_key

bp = Blueprint("auth", __name__, url_prefix="/auth")


def init_app(api_bp: Blueprint) -> None:
    api_bp.register_blueprint(bp)


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_password(password: str) -> tuple[bool, str]:
    """Validate password strength."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"
    return True, ""


@bp.post("/register")
def register():
    """Register a new user."""
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()

    # Validation
    if not email:
        return jsonify({"error": "Email is required"}), HTTPStatus.BAD_REQUEST
    if not validate_email(email):
        return jsonify({"error": "Invalid email format"}), HTTPStatus.BAD_REQUEST
    if not password:
        return jsonify({"error": "Password is required"}), HTTPStatus.BAD_REQUEST

    is_valid, error_msg = validate_password(password)
    if not is_valid:
        return jsonify({"error": error_msg}), HTTPStatus.BAD_REQUEST

    # Check if user already exists
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), HTTPStatus.CONFLICT

    # Create user
    try:
        user = User(email=email, name=name or email.split("@")[0])
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        token = generate_token(user)
        return (
            jsonify(
                {
                    "token": token,
                    "user": user.to_dict(),
                }
            ),
            HTTPStatus.CREATED,
        )
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Email already registered"}), HTTPStatus.CONFLICT
    except Exception as exc:
        current_app.logger.exception("Registration error")
        db.session.rollback()
        return jsonify({"error": "Registration failed"}), HTTPStatus.INTERNAL_SERVER_ERROR


@bp.post("/login")
def login():
    """Login a user."""
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), HTTPStatus.BAD_REQUEST

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), HTTPStatus.UNAUTHORIZED

    if not user.is_active:
        return jsonify({"error": "Account is inactive"}), HTTPStatus.FORBIDDEN

    token = generate_token(user)
    return jsonify({"token": token, "user": user.to_dict()})


@bp.get("/me")
@require_auth
def get_current_user_info(current_user: User):
    """Get current user information."""
    return jsonify({"user": current_user.to_dict()})


@bp.post("/logout")
@require_auth
def logout(current_user: User):
    """Logout (client should discard token)."""
    return jsonify({"message": "Logged out successfully"})


# API Key Management Routes

VALID_PROVIDERS = {"openai", "gemini", "grok", "anthropic"}


@bp.get("/api-keys")
@require_auth
def get_api_keys(current_user: User):
    """Get all API keys for the current user."""
    keys = UserAPIKey.query.filter_by(user_id=current_user.id, is_active=True).all()
    return jsonify({"api_keys": [key.to_dict() for key in keys]})


@bp.post("/api-keys")
@require_auth
def save_api_key(current_user: User):
    """Save or update an API key for a provider."""
    data = request.get_json() or {}
    provider = (data.get("provider") or "").strip().lower()
    api_key = (data.get("api_key") or "").strip()

    if not provider:
        return jsonify({"error": "Provider is required"}), HTTPStatus.BAD_REQUEST
    if provider not in VALID_PROVIDERS:
        return (
            jsonify({"error": f"Invalid provider. Must be one of: {', '.join(VALID_PROVIDERS)}"}),
            HTTPStatus.BAD_REQUEST,
        )
    if not api_key:
        return jsonify({"error": "API key is required"}), HTTPStatus.BAD_REQUEST

    # Encrypt the API key
    encrypted_key = encrypt_api_key(api_key)

    # Check if key already exists
    existing = UserAPIKey.query.filter_by(user_id=current_user.id, provider=provider).first()
    if existing:
        existing.encrypted_key = encrypted_key
        existing.is_active = True
    else:
        existing = UserAPIKey(
            user_id=current_user.id, provider=provider, encrypted_key=encrypted_key
        )
        db.session.add(existing)

    try:
        db.session.commit()
        return jsonify({"message": f"{provider} API key saved successfully", "api_key": existing.to_dict()})
    except Exception as exc:
        current_app.logger.exception("Error saving API key")
        db.session.rollback()
        return jsonify({"error": "Failed to save API key"}), HTTPStatus.INTERNAL_SERVER_ERROR


@bp.delete("/api-keys/<provider>")
@require_auth
def delete_api_key(provider: str, current_user: User):
    """Delete an API key for a provider."""
    provider = provider.lower()
    if provider not in VALID_PROVIDERS:
        return (
            jsonify({"error": f"Invalid provider. Must be one of: {', '.join(VALID_PROVIDERS)}"}),
            HTTPStatus.BAD_REQUEST,
        )

    key = UserAPIKey.query.filter_by(user_id=current_user.id, provider=provider).first()
    if not key:
        return jsonify({"error": "API key not found"}), HTTPStatus.NOT_FOUND

    key.is_active = False
    try:
        db.session.commit()
        return jsonify({"message": f"{provider} API key deleted successfully"})
    except Exception as exc:
        current_app.logger.exception("Error deleting API key")
        db.session.rollback()
        return jsonify({"error": "Failed to delete API key"}), HTTPStatus.INTERNAL_SERVER_ERROR


@bp.post("/api-keys/<provider>/validate")
@require_auth
def validate_api_key(provider: str, current_user: User):
    """Validate an API key for a provider (without saving it)."""
    provider = provider.lower()
    if provider not in VALID_PROVIDERS:
        return (
            jsonify({"error": f"Invalid provider. Must be one of: {', '.join(VALID_PROVIDERS)}"}),
            HTTPStatus.BAD_REQUEST,
        )

    data = request.get_json() or {}
    api_key = (data.get("api_key") or "").strip()

    if not api_key:
        return jsonify({"error": "API key is required"}), HTTPStatus.BAD_REQUEST

    # Basic format check
    if len(api_key) < 10:
        return jsonify({"valid": False, "error": "API key appears invalid (too short)"}), HTTPStatus.BAD_REQUEST

    # Make actual API call to validate the key
    try:
        from ..utils.api_key_validation import validate_api_key as validate_key_async
        import asyncio
        
        # Run async validation - handle event loop properly
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            # If loop is already running, we need to use a different approach
            # For now, create a new thread with a new event loop
            import threading
            result_container = {"is_valid": False, "error_msg": None, "done": False}
            
            def run_validation():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    is_valid, error_msg = new_loop.run_until_complete(validate_key_async(provider, api_key))
                    result_container["is_valid"] = is_valid
                    result_container["error_msg"] = error_msg
                finally:
                    new_loop.close()
                    result_container["done"] = True
            
            thread = threading.Thread(target=run_validation)
            thread.start()
            thread.join(timeout=15)  # 15 second timeout
            
            if not result_container["done"]:
                return jsonify({"valid": False, "error": "Validation timeout"}), HTTPStatus.REQUEST_TIMEOUT
            
            is_valid = result_container["is_valid"]
            error_msg = result_container["error_msg"]
        else:
            is_valid, error_msg = loop.run_until_complete(validate_key_async(provider, api_key))
        
        if is_valid:
            return jsonify({"valid": True, "message": "API key is valid"})
        else:
            return jsonify({"valid": False, "error": error_msg or "API key validation failed"}), HTTPStatus.BAD_REQUEST
    except Exception as exc:
        current_app.logger.exception("Error validating API key")
        return jsonify({"valid": False, "error": f"Validation error: {str(exc)[:200]}"}), HTTPStatus.INTERNAL_SERVER_ERROR


def get_user_api_key(user_id: str, provider: str) -> str | None:
    """Get a decrypted API key for a user and provider."""
    key = UserAPIKey.query.filter_by(user_id=user_id, provider=provider, is_active=True).first()
    if not key:
        return None
    try:
        return decrypt_api_key(key.encrypted_key)
    except Exception:
        current_app.logger.exception(f"Error decrypting API key for user {user_id}, provider {provider}")
        return None

