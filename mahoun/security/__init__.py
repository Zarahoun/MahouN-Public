"""
Security Hardening Module
==========================

Enterprise-grade security features for production deployment.

Features:
- Rate limiting with sliding window
- OAuth2/JWT authentication
- Prompt injection defense
- API key management
- Security audit logging
- AES-256-GCM encryption (data at rest/in transit)
- Ed25519 digital signatures (ledger integrity)
"""

from mahoun.security.rate_limiter import RateLimiter, RateLimitExceeded
from mahoun.security.auth import JWTAuthenticator, OAuth2Handler
from mahoun.security.prompt_defense import PromptInjectionDefender
from mahoun.security.api_keys import APIKeyManager
from mahoun.security.encryption import (
    AESEncryption,
    EnvelopeEncryption,
    EncryptionKey,
    EncryptedData,
    get_aes_encryption,
    get_envelope_encryption,
)
from mahoun.security.signing import (
    Ed25519Signing,
    LedgerSigning,
    SigningKeyPair,
    Signature,
    get_ed25519_signing,
    get_ledger_signing,
)

__all__ = [
    # Rate limiting & auth
    "RateLimiter",
    "RateLimitExceeded",
    "JWTAuthenticator",
    "OAuth2Handler",
    "PromptInjectionDefender",
    "APIKeyManager",
    # Encryption
    "AESEncryption",
    "EnvelopeEncryption",
    "EncryptionKey",
    "EncryptedData",
    "get_aes_encryption",
    "get_envelope_encryption",
    # Signing
    "Ed25519Signing",
    "LedgerSigning",
    "SigningKeyPair",
    "Signature",
    "get_ed25519_signing",
    "get_ledger_signing",
]
