"""
MCP Tool Registry (HAJIX Refactored)
=====================================

Central registry for all MCP tools.
"""

from mahoun.mcp.tools.graph import GraphTool
from mahoun.mcp.tools.rag import RAGTool
from mahoun.mcp.tools.ingest import IngestTool
from mahoun.mcp.tools.maintenance import MaintenanceTool
from mahoun.mcp.tools.system import SystemTool


# Tool instances registry
TOOLS = {
    "Graph": GraphTool(),
    "RAG": RAGTool(),
    "Ingest": IngestTool(),
    "Maintenance": MaintenanceTool(),
    "System": SystemTool(),
}
