"""
CLI Authentication Helper
===========================

Provides authentication for CLI scripts to access the canonical API.

This helper:
1. Fetches JWT tokens from the API endpoint
2. Stores tokens securely in environment/config
3. Allows CLI scripts to authenticate without disrupting global auth
"""

import os
import json
from pathlib import Path
from typing import Optional
import logging
import requests
from datetime import datetime, timezone
from api.security_config import get_jwt_secret

logger = logging.getLogger(__name__)


# Default API URL
DEFAULT_API_URL = "http://localhost:8080"

# Simple auth token (for development only)
SIMPLE_AUTH_TOKEN = os.getenv("SIMPLE_AUTH_TOKEN", "mahoun-cli-secret-token-2024")


def get_api_url() -> str:
    """Get API URL from environment or use default."""
    return os.getenv("MAHOUN_API_URL", DEFAULT_API_URL)


def get_cli_token_path() -> Path:
    """Get path to CLI token storage."""
    # Store in .devin directory or config directory
    devin_dir = Path.home() / ".devin"
    devin_dir.mkdir(exist_ok=True)
    return devin_dir / "mahoun_cli_token.json"


def fetch_cli_token_from_api() -> str:
    """
    Fetch CLI token from API login endpoint.

    This calls the public login endpoint with ingestion_cli credentials
    to get a service principal token.

    Returns:
        JWT token string
    """
    api_url = get_api_url()
    login_endpoint = f"{api_url}/api/v1/auth/login"

    try:
        # Use ingestion_cli credentials from MOCK_USERS_DB
        login_data = {
            "username": "ingestion_cli",
            "password": "cli-service-principal"
        }

        response = requests.post(login_endpoint, json=login_data, timeout=30, headers={"Content-Type": "application/json"})
        response.raise_for_status()

        token_data = response.json()
        token = token_data.get("access_token")

        if not token:
            raise ValueError("No token in response")

        # Store token metadata
        stored_data = {
            "token": token,
            "username": "ingestion_cli",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_in_days": 365
        }

        token_path = get_cli_token_path()
        with open(token_path, "w") as f:
            json.dump(stored_data, f, indent=2)

        logger.info(f"CLI token fetched from API and stored at {token_path}")
        return token

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch CLI token from API: {e}")
        raise RuntimeError(
            f"Cannot connect to API at {api_url}. "
            "Please ensure the API server is running."
        )
    except Exception as e:
        logger.error(f"Failed to process CLI token response: {e}")
        raise


def load_cli_token() -> Optional[str]:
    """
    Load stored CLI token.

    Returns:
        JWT token string if available, None otherwise
    """
    token_path = get_cli_token_path()
    if not token_path.exists():
        logger.warning(f"CLI token not found at {token_path}")
        return None

    try:
        with open(token_path, "r") as f:
            token_data = json.load(f)
        return token_data.get("token")
    except Exception as e:
        logger.error(f"Failed to load CLI token: {e}")
        return None


def get_cli_auth_header() -> Optional[str]:
    """
    Get Authorization header for CLI requests using simple token.

    Returns:
        Bearer token string if available, None otherwise
    """
    token = load_cli_token()
    if token:
        return f"Bearer {token}"
    
    # If no stored token, use simple token directly
    return f"Bearer {SIMPLE_AUTH_TOKEN}"


def ensure_cli_token() -> str:
    """
    Ensure CLI token exists - use simple token directly.

    Returns:
        Simple auth token string
    """
    # For simple auth, just return the token directly
    return SIMPLE_AUTH_TOKEN


def validate_cli_token() -> bool:
    """
    Validate that CLI token is properly configured.

    For simple auth, just check if the token is not empty.

    Returns:
        True if token is valid, False otherwise
    """
    token = load_cli_token()
    if token:
        return len(token) > 0
    
    # Simple token is always valid
    return len(SIMPLE_AUTH_TOKEN) > 0


def get_cli_service_principal() -> dict:
    """Get CLI service principal info."""
    return {
        "username": "ingestion_cli",
        "email": "ingestion-cli@mahoun.ai",
        "full_name": "MAHOUN Ingestion CLI Service",
        "role": "ANALYST",
        "is_active": True,
    }


DEFAULT_SIMPLE_ACTOR_ID = "12345678-1234-5678-9012-123456789abc"


def get_cli_actor_id() -> str:
    """Return canonical actor UUID matching api.auth.dependencies.get_current_user."""
    return os.getenv("MAHOUN_CLI_ACTOR_ID", DEFAULT_SIMPLE_ACTOR_ID)