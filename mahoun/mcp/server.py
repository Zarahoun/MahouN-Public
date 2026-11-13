"""
MCP Server (Production-Grade)
==============================

JSON-RPC 2.0 server for MCP (Model Context Protocol) interface.

Security Features:
    - API Key authentication
    - Rate limiting
    - Request/response logging
    - Comprehensive error handling

Endpoints:
    POST /mcp - Execute tool method via JSON-RPC
    GET /mcp/tools - List available tools
    GET /health - Health check

Usage:
    export MCP_API_KEY="your-secret-key-here"
    uvicorn mahoun.mcp.server:app --host 0.0.0.0 --port 8000
"""

from typing import Any, Dict, Optional, Union
import logging
import time

from fastapi import FastAPI, Security, HTTPException, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, field_validator
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
except ImportError:
    class Limiter:
        def __init__(self, key_func=None, *args, **kwargs):
            pass
        def limit(self, limit_value):
            def decorator(func):
                return func
            return decorator

    class RateLimitExceeded(Exception):
        pass

    def _rate_limit_exceeded_handler(request, exc):
        pass

    def get_remote_address():
        return "127.0.0.1"
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from mahoun.mcp.registry import TOOLS
from mahoun.core.settings import load_security_settings
from mahoun.core.governance.governance_context import GovernanceContextManager
from mahoun.core.governance.violations import GovernanceViolationError

logger = logging.getLogger(__name__)

# Fail fast on invalid security configuration
SECURITY_SETTINGS = load_security_settings()

# Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="MAHOUN MCP Server (Production)",
    description="Secure Model Context Protocol interface for MAHOUN",
    version="2.1.0"
)

# Security Middlewares
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=SECURITY_SETTINGS.allowed_hosts
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=SECURITY_SETTINGS.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
MCP_API_KEY = SECURITY_SETTINGS.api_key

# JSON-RPC Error Codes
class ErrorCode:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    # Custom errors
    DB_UNAVAILABLE = -32001
    TIMEOUT = -32002
    UNAUTHORIZED = -32003
    RATE_LIMITED = -32004
    GOVERNANCE_VIOLATION = -32005


class MCPRequest(BaseModel):
    """JSON-RPC 2.0 request model."""
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Union[int, str]
    
    @field_validator('jsonrpc')
    @classmethod
    def validate_jsonrpc(cls, v):
        if v != "2.0":
            raise ValueError('jsonrpc must be "2.0"')
        return v


class MCPResponse(BaseModel):
    """JSON-RPC 2.0 response model."""
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Union[int, str]


class MCPError(BaseModel):
    """JSON-RPC 2.0 error object."""
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None


def verify_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    """Verify API key from header."""
    if MCP_API_KEY is None:
        return "dev"
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    if api_key != MCP_API_KEY:
        logger.warning(f"Invalid API key attempt: {api_key[:8]}...")
        raise HTTPException(
            status_code=403,
            detail="Invalid API key"
        )
    
    return api_key


def create_error_response(code: int, message: str, request_id: Union[int, str], data: Optional[Dict] = None) -> Dict[str, Any]:
    """Create standardized JSON-RPC error response."""
    error = {
        "code": code,
        "message": message
    }
    if data:
        error["data"] = data
    
    return {
        "jsonrpc": "2.0",
        "error": error,
        "id": request_id
    }


@app.post("/mcp")
@limiter.limit("100/minute")
async def mcp_handler(
    request: Request,
    req: MCPRequest,
    api_key: str = Security(verify_api_key)
) -> Dict[str, Any]:
    """
    Handle MCP JSON-RPC 2.0 request with full security and error handling.
    
    Security:
        - Requires valid API key in X-API-Key header
        - Rate limited to 100 requests/minute per IP
    
    Args:
        request: FastAPI request object (for rate limiting)
        req: MCPRequest with method, params, and id
        api_key: Verified API key from header
        
    Returns:
        JSON-RPC 2.0 response with result or error
    """
    start_time = time.time()
    
    try:
        # Validate method format
        if "." not in req.method:
            return create_error_response(
                ErrorCode.INVALID_REQUEST,
                "Method must be in format 'ToolName.functionName'",
                req.id,
                {"method": req.method}
            )
        
        tool_name, func_name = req.method.split(".", 1)
        
        # Get tool
        if tool_name not in TOOLS:
            return create_error_response(
                ErrorCode.METHOD_NOT_FOUND,
                f"Tool '{tool_name}' not found",
                req.id,
                {"available_tools": list(TOOLS.keys())}
            )
        
        tool = TOOLS[tool_name]
        
        # Get function
        if not hasattr(tool, func_name):
            available_methods = [
                m for m in dir(tool)
                if not m.startswith("_") and callable(getattr(tool, m))
            ]
            return create_error_response(
                ErrorCode.METHOD_NOT_FOUND,
                f"Function '{func_name}' not found in tool '{tool_name}'",
                req.id,
                {"available_methods": available_methods}
            )
        
        func = getattr(tool, func_name)
        
        # Execute (with async support and MANDATORY governance context)
        params = req.params or {}
        
        import asyncio
        async with GovernanceContextManager.active_context(correlation_id=str(req.id)):
            if asyncio.iscoroutinefunction(func):
                result = await func(**params)
            else:
                result = func(**params)
        
        duration_ms = (time.time() - start_time) * 1000
        
        logger.info(
            f"MCP call succeeded",
            extra={
                "method": req.method,
                "params_keys": list(params.keys()),
                "duration_ms": duration_ms,
                "request_id": req.id
            }
        )
        
        return {
            "jsonrpc": "2.0",
            "result": result,
            "id": req.id
        }
    
    except GovernanceViolationError as e:
        logger.error(f"Governance violation in MCP call: {e}")
        return create_error_response(
            ErrorCode.GOVERNANCE_VIOLATION,
            "Governance boundary violation detected",
            req.id,
            {
                "category": e.violation.category.value,
                "message": e.violation.message,
                "source": e.violation.source
            }
        )
    
    except ValueError as e:
        # Invalid parameters
        return create_error_response(
            ErrorCode.INVALID_PARAMS,
            str(e),
            req.id
        )
    
    except TimeoutError as e:
        return create_error_response(
            ErrorCode.TIMEOUT,
            "Request timeout",
            req.id,
            {"details": str(e)}
        )
    
    except ConnectionError as e:
        return create_error_response(
            ErrorCode.DB_UNAVAILABLE,
            "Database connection failed",
            req.id,
            {"details": str(e)}
        )

    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(
            f"MCP call failed with unexpected error",
            extra={
                "method": req.method,
                "error": str(e),
                "error_type": type(e).__name__,
                "request_id": req.id
            },
            exc_info=True
        )
        
        return create_error_response(
            ErrorCode.INTERNAL_ERROR,
            "Internal server error",
            req.id,
            {
                "error_type": type(e).__name__,
                "message": str(e)
            }
        )


@app.get("/mcp/tools")
def list_tools() -> Dict[str, Any]:
    """
    List available MCP tools.
    
    Returns:
        Dictionary with tool names and their methods
    """
    tools_info: Dict[str, Any] = {}
    for name, tool in TOOLS.items():
        methods = [
            method for method in dir(tool)
            if not method.startswith("_") and callable(getattr(tool, method))
        ]
        tools_info[name] = {"methods": methods}
    
    return {"tools": tools_info}


@app.get("/health")
def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
