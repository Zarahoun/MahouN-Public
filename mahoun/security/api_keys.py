"""
API Key Management
==================

Secure API key generation, validation, and management.

Features:
- Cryptographically secure key generation
- Key hashing and storage
- Key rotation
- Usage tracking
- Rate limiting per key
"""

import secrets
import hashlib
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class KeyStatus(str, Enum):
    """API key status."""
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    SUSPENDED = "suspended"


@dataclass
class APIKey:
    """API key metadata."""
    key_id: str
    key_hash: str
    name: str
    created_at: datetime
    expires_at: Optional[datetime]
    status: KeyStatus
    permissions: List[str] = field(default_factory=list)
    rate_limit: Optional[int] = None  # Requests per minute
    usage_count: int = 0
    last_used: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "key_id": self.key_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "status": self.status.value,
            "permissions": self.permissions,
            "rate_limit": self.rate_limit,
            "usage_count": self.usage_count,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "metadata": self.metadata
        }


class APIKeyManager:
    """
    Manage API keys securely.
    
    Keys are hashed before storage. Only the hash is stored, never the raw key.
    """
    
    KEY_PREFIX = "mhn_"  # Mahoun key prefix
    KEY_LENGTH = 32  # bytes
    
    def __init__(self):
        """Initialize API key manager."""
        # In production, use database
        self.keys: Dict[str, APIKey] = {}
    
    def generate_key(
        self,
        name: str,
        permissions: Optional[List[str]] = None,
        expires_in_days: Optional[int] = None,
        rate_limit: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> tuple[str, APIKey]:
        """
        Generate new API key.
        
        Args:
            name: Key name/description
            permissions: List of permissions
            expires_in_days: Expiry in days (None = no expiry)
            rate_limit: Rate limit (requests per minute)
            metadata: Additional metadata
            
        Returns:
            Tuple of (raw_key, api_key_object)
        """
        # Generate cryptographically secure key
        raw_key = secrets.token_urlsafe(self.KEY_LENGTH)
        full_key = f"{self.KEY_PREFIX}{raw_key}"
        
        # Hash the key
        key_hash = self._hash_key(full_key)
        
        # Generate key ID
        key_id = secrets.token_urlsafe(16)
        
        # Calculate expiry
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        
        # Create key object
        api_key = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            name=name,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            status=KeyStatus.ACTIVE,
            permissions=permissions or [],
            rate_limit=rate_limit,
            metadata=metadata or {}
        )
        
        # Store key
        self.keys[key_hash] = api_key
        
        logger.info(f"Generated API key: {key_id} ({name})")
        return full_key, api_key
    
    def _hash_key(self, key: str) -> str:
        """
        Hash API key using SHA256.
        
        Args:
            key: Raw API key
            
        Returns:
            Hex digest of hash
        """
        return hashlib.sha256(key.encode()).hexdigest()
    
    def validate_key(self, key: str) -> Optional[APIKey]:
        """
        Validate API key.
        
        Args:
            key: Raw API key
            
        Returns:
            APIKey object if valid, None otherwise
        """
        key_hash = self._hash_key(key)
        
        if key_hash not in self.keys:
            logger.warning("Invalid API key attempted")
            return None
        
        api_key = self.keys[key_hash]
        
        # Check status
        if api_key.status != KeyStatus.ACTIVE:
            logger.warning(f"Inactive key used: {api_key.key_id} ({api_key.status})")
            return None
        
        # Check expiry
        if api_key.expires_at and datetime.now(timezone.utc) > api_key.expires_at:
            logger.warning(f"Expired key used: {api_key.key_id}")
            api_key.status = KeyStatus.EXPIRED
            return None
        
        # Update usage
        api_key.usage_count += 1
        api_key.last_used = datetime.now(timezone.utc)
        
        return api_key
    
    def revoke_key(self, key_id: str) -> bool:
        """
        Revoke API key.
        
        Args:
            key_id: Key ID to revoke
            
        Returns:
            True if revoked, False if not found
        """
        for api_key in self.keys.values():
            if api_key.key_id == key_id:
                api_key.status = KeyStatus.REVOKED
                logger.info(f"Revoked API key: {key_id}")
                return True
        
        logger.warning(f"Key not found for revocation: {key_id}")
        return False
    
    def suspend_key(self, key_id: str) -> bool:
        """
        Suspend API key (can be reactivated).
        
        Args:
            key_id: Key ID to suspend
            
        Returns:
            True if suspended, False if not found
        """
        for api_key in self.keys.values():
            if api_key.key_id == key_id:
                api_key.status = KeyStatus.SUSPENDED
                logger.info(f"Suspended API key: {key_id}")
                return True
        
        return False
    
    def reactivate_key(self, key_id: str) -> bool:
        """
        Reactivate suspended key.
        
        Args:
            key_id: Key ID to reactivate
            
        Returns:
            True if reactivated, False if not found or not suspended
        """
        for api_key in self.keys.values():
            if api_key.key_id == key_id:
                if api_key.status == KeyStatus.SUSPENDED:
                    api_key.status = KeyStatus.ACTIVE
                    logger.info(f"Reactivated API key: {key_id}")
                    return True
                else:
                    logger.warning(f"Cannot reactivate key in status: {api_key.status}")
                    return False
        
        return False
    
    def rotate_key(self, key_id: str) -> Optional[tuple[str, APIKey]]:
        """
        Rotate API key (generate new key, revoke old).
        
        Args:
            key_id: Key ID to rotate
            
        Returns:
            Tuple of (new_key, api_key_object) or None if not found
        """
        # Find old key
        old_key = None
        for api_key in self.keys.values():
            if api_key.key_id == key_id:
                old_key = api_key
                break
        
        if not old_key:
            logger.warning(f"Key not found for rotation: {key_id}")
            return None
        
        # Generate new key with same properties
        new_key, new_api_key = self.generate_key(
            name=old_key.name,
            permissions=old_key.permissions,
            expires_in_days=None,  # Reset expiry
            rate_limit=old_key.rate_limit,
            metadata={**old_key.metadata, "rotated_from": key_id}
        )
        
        # Revoke old key
        old_key.status = KeyStatus.REVOKED
        
        logger.info(f"Rotated API key: {key_id} -> {new_api_key.key_id}")
        return new_key, new_api_key
    
    def list_keys(
        self,
        status: Optional[KeyStatus] = None,
        include_expired: bool = False
    ) -> List[APIKey]:
        """
        List API keys.
        
        Args:
            status: Filter by status
            include_expired: Include expired keys
            
        Returns:
            List of APIKey objects
        """
        keys = list(self.keys.values())
        
        if status:
            keys = [k for k in keys if k.status == status]
        
        if not include_expired:
            now = datetime.now(timezone.utc)
            keys = [
                k for k in keys
                if not k.expires_at or k.expires_at > now
            ]
        
        # Sort by created_at (newest first)
        keys.sort(key=lambda k: k.created_at, reverse=True)
        return keys
    
    def get_key_info(self, key_id: str) -> Optional[APIKey]:
        """
        Get key information.
        
        Args:
            key_id: Key ID
            
        Returns:
            APIKey object or None
        """
        for api_key in self.keys.values():
            if api_key.key_id == key_id:
                return api_key
        return None
    
    def check_permission(self, key: str, required_permission: str) -> bool:
        """
        Check if key has required permission.
        
        Args:
            key: Raw API key
            required_permission: Required permission
            
        Returns:
            True if key has permission
        """
        api_key = self.validate_key(key)
        if not api_key:
            return False
        
        # Wildcard permission
        if "*" in api_key.permissions:
            return True
        
        return required_permission in api_key.permissions
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get key usage statistics.
        
        Returns:
            Statistics dictionary
        """
        total_keys = len(self.keys)
        active_keys = sum(1 for k in self.keys.values() if k.status == KeyStatus.ACTIVE)
        revoked_keys = sum(1 for k in self.keys.values() if k.status == KeyStatus.REVOKED)
        total_usage = sum(k.usage_count for k in self.keys.values())
        
        return {
            "total_keys": total_keys,
            "active_keys": active_keys,
            "revoked_keys": revoked_keys,
            "total_usage": total_usage,
            "average_usage": total_usage / total_keys if total_keys > 0 else 0
        }
