"""
JWT and OAuth2 Authentication
==============================

Enterprise-grade authentication with JWT tokens and OAuth2 support.

Features:
- JWT token generation and validation
- OAuth2 authorization code flow
- Token refresh mechanism
- Role-based access control (RBAC)
- Token blacklisting
"""

try:
    import jwt
except ImportError:
    jwt = None
import secrets
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    """User roles for RBAC."""
    ADMIN = "admin"
    USER = "user"
    READONLY = "readonly"
    SERVICE = "service"


@dataclass
class TokenPayload:
    """JWT token payload."""
    user_id: str
    roles: List[str]
    exp: datetime
    iat: datetime
    jti: str  # JWT ID for blacklisting


class JWTAuthenticator:
    """
    JWT-based authentication.
    
    Provides token generation, validation, and refresh.
    """
    
    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7
    ):
        """
        Initialize JWT authenticator.
        
        Args:
            secret_key: Secret key for signing tokens
            algorithm: JWT algorithm (HS256, RS256, etc.)
            access_token_expire_minutes: Access token expiry
            refresh_token_expire_days: Refresh token expiry
        """
        if jwt is None:
            raise RuntimeError("PyJWT is not installed. Install with 'pip install PyJWT'")
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days
        
        # Token blacklist (in production, use Redis)
        self.blacklist: set = set()
    
    def create_access_token(
        self,
        user_id: str,
        roles: Optional[List[str]] = None
    ) -> str:
        """
        Create JWT access token.
        
        Args:
            user_id: User identifier
            roles: User roles
            
        Returns:
            JWT token string
        """
        now = datetime.now(timezone.utc)
        exp = now + timedelta(minutes=self.access_token_expire_minutes)
        jti = secrets.token_urlsafe(16)
        
        payload = {
            "user_id": user_id,
            "roles": roles or [UserRole.USER],
            "exp": exp,
            "iat": now,
            "jti": jti,
            "type": "access"
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        logger.debug(f"Created access token for user {user_id}")
        return token
    
    def create_refresh_token(self, user_id: str) -> str:
        """
        Create JWT refresh token.
        
        Args:
            user_id: User identifier
            
        Returns:
            JWT refresh token string
        """
        now = datetime.now(timezone.utc)
        exp = now + timedelta(days=self.refresh_token_expire_days)
        jti = secrets.token_urlsafe(16)
        
        payload = {
            "user_id": user_id,
            "exp": exp,
            "iat": now,
            "jti": jti,
            "type": "refresh"
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        logger.debug(f"Created refresh token for user {user_id}")
        return token
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify and decode JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded token payload
            
        Raises:
            jwt.InvalidTokenError: If token is invalid
            ValueError: If token is blacklisted
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            
            # Check blacklist
            jti = payload.get("jti")
            if jti and jti in self.blacklist:
                raise ValueError("Token has been revoked")
            
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            raise
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            raise
    
    def refresh_access_token(self, refresh_token: str) -> str:
        """
        Create new access token from refresh token.
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            New access token
            
        Raises:
            ValueError: If refresh token is invalid
        """
        payload = self.verify_token(refresh_token)
        
        if payload.get("type") != "refresh":
            raise ValueError("Not a refresh token")
        
        user_id = payload["user_id"]
        return self.create_access_token(user_id)
    
    def revoke_token(self, token: str) -> None:
        """
        Revoke token by adding to blacklist.
        
        Args:
            token: Token to revoke
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False}  # Allow expired tokens to be revoked
            )
            jti = payload.get("jti")
            if jti:
                self.blacklist.add(jti)
                logger.info(f"Token {jti} revoked")
        except jwt.InvalidTokenError:
            logger.warning("Cannot revoke invalid token")
    
    def has_role(self, token: str, required_role: str) -> bool:
        """
        Check if token has required role.
        
        Args:
            token: JWT token
            required_role: Required role
            
        Returns:
            True if user has role
        """
        try:
            payload = self.verify_token(token)
            roles = payload.get("roles", [])
            return required_role in roles or UserRole.ADMIN in roles
        except Exception:
            return False


class OAuth2Handler:
    """
    OAuth2 authorization code flow handler.
    
    Supports standard OAuth2 providers (Google, GitHub, etc.)
    """
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        authorization_endpoint: str,
        token_endpoint: str
    ):
        """
        Initialize OAuth2 handler.
        
        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            redirect_uri: Redirect URI after authorization
            authorization_endpoint: Provider's authorization URL
            token_endpoint: Provider's token URL
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.authorization_endpoint = authorization_endpoint
        self.token_endpoint = token_endpoint
        
        # State storage (in production, use Redis)
        self.states: Dict[str, Dict[str, Any]] = {}
    
    def get_authorization_url(self, scope: Optional[List[str]] = None) -> tuple[str, str]:
        """
        Generate authorization URL.
        
        Args:
            scope: OAuth2 scopes
            
        Returns:
            Tuple of (authorization_url, state)
        """
        state = secrets.token_urlsafe(32)
        scope_str = " ".join(scope or ["openid", "profile", "email"])
        
        # Store state
        self.states[state] = {
            "created_at": datetime.now(timezone.utc),
            "scope": scope_str
        }
        
        url = (
            f"{self.authorization_endpoint}"
            f"?client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&response_type=code"
            f"&scope={scope_str}"
            f"&state={state}"
        )
        
        logger.debug(f"Generated authorization URL with state {state}")
        return url, state
    
    def verify_state(self, state: str) -> bool:
        """
        Verify OAuth2 state parameter.
        
        Args:
            state: State parameter from callback
            
        Returns:
            True if state is valid
        """
        if state not in self.states:
            return False
        
        # Check expiry (5 minutes)
        state_data = self.states[state]
        created_at = state_data["created_at"]
        if (datetime.now(timezone.utc) - created_at).total_seconds() > 300:
            del self.states[state]
            return False
        
        return True
    
    def exchange_code_for_token(self, code: str, state: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code
            state: State parameter
            
        Returns:
            Token response from provider
            
        Raises:
            ValueError: If state is invalid
        """
        if not self.verify_state(state):
            raise ValueError("Invalid or expired state")
        
        # In production, make actual HTTP request to token endpoint
        # For now, return mock response
        logger.info(f"Exchanging code for token (state: {state})")
        
        # Clean up state
        del self.states[state]
        
        return {
            "access_token": "mock_access_token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "mock_refresh_token"
        }
    
    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get user info from provider.
        
        Args:
            access_token: OAuth2 access token
            
        Returns:
            User information
        """
        # In production, make actual HTTP request to userinfo endpoint
        logger.info("Fetching user info")
        
        return {
            "sub": "user123",
            "email": "user@example.com",
            "name": "Test User"
        }
