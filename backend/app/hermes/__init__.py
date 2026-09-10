"""Hermes orchestration layer: MCP tool surface between GPT-5.5 and AutoHH domain.

Principle: GPT-5.5 thinks → Hermes orchestrates → AutoHH executes → PostgreSQL stores.

Hermes never writes to PostgreSQL, OAuth tokens, or cookies directly. It delegates
all persistence and integrations to the AutoHH domain services. The only state
Hermes owns is policy evaluation and the approval gate for autonomous actions.
"""

from app.hermes.mcp_tools import McpToolError, ToolContext, ToolResult
from app.hermes.modes import AutonomyMode

__all__ = [
    "AutonomyMode",
    "McpToolError",
    "ToolContext",
    "ToolResult",
]
