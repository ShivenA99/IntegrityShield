"""Authentication routes."""

from __future__ import annotations

import asyncio
import re
import threading
import uuid
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
    """DEPRECATED: Email/password registration is no longer supported."""
    return jsonify({
        "error": "Email/password registration is no longer supported",
        "message": "Please use /auth/login-with-key to authenticate with your OpenAI API key",
        "new_endpoint": "/auth/login-with-key"
    }), HTTPStatus.GONE


@bp.post("/login")
def login():
    """DEPRECATED: Email/password login is no longer supported."""
    return jsonify({
        "error": "Email/password login is no longer supported",
        "message": "Please use /auth/login-with-key to authenticate with your OpenAI API key",
        "new_endpoint": "/auth/login-with-key"
    }), HTTPStatus.GONE


@bp.post("/login-with-key")
def login_with_openai_key():
    """Authenticate user with OpenAI API key."""
    data = request.get_json() or {}
    api_key = (data.get("openai_api_key") or "").strip()
    email = (data.get("email") or "").strip().lower() if data.get("email") else None

    # Validate key format
    if not api_key or not api_key.startswith("sk-"):
        return jsonify({"error": "Invalid OpenAI API key format (must start with 'sk-')"}), HTTPStatus.BAD_REQUEST

    # Validate email if provided
    if email and not validate_email(email):
        return jsonify({"error": "Invalid email format"}), HTTPStatus.BAD_REQUEST

    # Validate key against OpenAI API
    from ..utils.api_key_validation import validate_openai_key

    # Run async validation with event loop handling
    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # If loop is already running, use threading approach
            result_container = {"is_valid": False, "error_msg": None, "done": False}

            def run_validation():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    is_valid, error_msg = new_loop.run_until_complete(validate_openai_key(api_key))
                    result_container["is_valid"] = is_valid
                    result_container["error_msg"] = error_msg
                finally:
                    new_loop.close()
                    result_container["done"] = True

            thread = threading.Thread(target=run_validation)
            thread.start()
            thread.join(timeout=15)  # 15 second timeout

            if not result_container["done"]:
                return jsonify({"error": "OpenAI API validation timeout"}), HTTPStatus.REQUEST_TIMEOUT

            is_valid = result_container["is_valid"]
            error_msg = result_container["error_msg"]
        else:
            is_valid, error_msg = loop.run_until_complete(validate_openai_key(api_key))
    except Exception as exc:
        current_app.logger.exception("Error validating OpenAI key")
        return jsonify({"error": f"Validation error: {str(exc)[:200]}"}), HTTPStatus.INTERNAL_SERVER_ERROR

    if not is_valid:
        return jsonify({
            "error": "Invalid OpenAI API key",
            "details": error_msg or "OpenAI API key validation failed"
        }), HTTPStatus.UNAUTHORIZED

    # Find or create user by key hash
    key_hash = User.hash_openai_key(api_key)
    user = User.query.filter_by(openai_key_hash=key_hash).first()

    try:
        if user:
            # Existing user - update key and email
            user.set_openai_key(api_key)
            if email:
                user.email = email
            user.is_active = True
        else:
            # New user - create
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                name=email.split("@")[0] if email else f"User_{key_hash[:8]}",
                is_active=True
            )
            user.set_openai_key(api_key)
            db.session.add(user)

        db.session.commit()

        # Generate JWT token
        token = generate_token(user)

        return jsonify({
            "token": token,
            "user": user.to_dict()
        }), HTTPStatus.OK
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "User creation failed (duplicate key)"}), HTTPStatus.CONFLICT
    except Exception as exc:
        current_app.logger.exception("Login with key error")
        db.session.rollback()
        return jsonify({"error": "Authentication failed"}), HTTPStatus.INTERNAL_SERVER_ERROR


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


@bp.post("/validate-session")
@require_auth
def validate_session(current_user: User):
    """Validate that user's OpenAI key is still valid."""
    from ..utils.api_key_validation import validate_openai_key

    # Get user's OpenAI key
    openai_key = current_user.get_openai_key()
    if not openai_key:
        # User doesn't have OpenAI key - mark inactive
        current_user.is_active = False
        db.session.commit()
        return jsonify({
            "valid": False,
            "error": "No OpenAI API key found"
        }), HTTPStatus.UNAUTHORIZED

    # Run async validation with event loop handling
    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # If loop is already running, use threading approach
            result_container = {"is_valid": False, "error_msg": None, "done": False}

            def run_validation():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    is_valid, error_msg = new_loop.run_until_complete(validate_openai_key(openai_key))
                    result_container["is_valid"] = is_valid
                    result_container["error_msg"] = error_msg
                finally:
                    new_loop.close()
                    result_container["done"] = True

            thread = threading.Thread(target=run_validation)
            thread.start()
            thread.join(timeout=15)  # 15 second timeout

            if not result_container["done"]:
                return jsonify({
                    "valid": False,
                    "error": "OpenAI API validation timeout"
                }), HTTPStatus.REQUEST_TIMEOUT

            is_valid = result_container["is_valid"]
            error_msg = result_container["error_msg"]
        else:
            is_valid, error_msg = loop.run_until_complete(validate_openai_key(openai_key))
    except Exception as exc:
        current_app.logger.exception("Error validating OpenAI key in session")
        return jsonify({
            "valid": False,
            "error": f"Validation error: {str(exc)[:200]}"
        }), HTTPStatus.INTERNAL_SERVER_ERROR

    if not is_valid:
        # Mark user as inactive and force logout
        current_user.is_active = False
        db.session.commit()
        return jsonify({
            "valid": False,
            "error": error_msg or "OpenAI API key is no longer valid"
        }), HTTPStatus.UNAUTHORIZED

    # Key is valid - return success
    return jsonify({
        "valid": True,
        "user": current_user.to_dict()
    }), HTTPStatus.OK


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

