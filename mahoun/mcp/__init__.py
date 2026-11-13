"""
MCP Package - Model Context Protocol for MAHOUN.

Note: The server module requires fastapi to be installed.
"""
from typing import Any, Optional

from .registry import TOOLS

__all__ = ["TOOLS"]

# Optional imports - only available if fastapi is installed
try:
    from .server import app, MCPRequest, mcp_handler
    __all__.extend(["app", "MCPRequest", "mcp_handler"])
except ImportError:
    app: Optional[Any] = None
    MCPRequest: Optional[Any] = None
    mcp_handler: Optional[Any] = None
