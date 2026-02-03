"""Compatibility shim for MCP tool registry.

The implementation moved to `src.domains.mcp.registry`.
"""

from src.domains.mcp.registry import (  # noqa: F401
    GROK_TOOLS,
    get_tool_definitions,
    get_tool_registry,
)
