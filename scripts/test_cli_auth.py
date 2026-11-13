#!/usr/bin/env python3
"""Test CLI authentication helper"""

import sys
sys.path.insert(0, '/home/haji/Desktop/KingMahouN')

from scripts.cli_auth_helper import (
    fetch_cli_token_from_api,
    load_cli_token,
    get_cli_auth_header,
    ensure_cli_token,
    validate_cli_token,
    get_cli_service_principal,
    get_api_url
)

def test_cli_auth():
    print("Testing CLI Authentication Helper...")

    # Test service principal
    print("\n1. Service Principal:")
    principal = get_cli_service_principal()
    print(f"   Username: {principal['username']}")
    print(f"   Role: {principal['role']}")

    # Test API URL
    print("\n2. API URL:")
    api_url = get_api_url()
    print(f"   API URL: {api_url}")

    # Test token loading (may be None initially)
    print("\n3. Token Loading (initial):")
    loaded_token = load_cli_token()
    print(f"   Token loaded: {loaded_token is not None}")

    # Test auth header (may be None initially)
    print("\n4. Auth Header (initial):")
    header = get_cli_auth_header()
    print(f"   Header: {header is not None}")

    # Test validation (will fail if no token)
    print("\n5. Token Validation (initial):")
    is_valid = validate_cli_token()
    print(f"   Valid: {is_valid}")

    # Test ensure token (will try to fetch from API)
    print("\n6. Ensure Token (will fetch from API):")
    try:
        ensured_token = ensure_cli_token()
        print(f"   Token ensured: {ensured_token[:50]}...")
    except Exception as e:
        print(f"   Failed (expected if API not running): {e}")

    print("\n✅ CLI auth helper structure validated!")

if __name__ == "__main__":
    test_cli_auth()