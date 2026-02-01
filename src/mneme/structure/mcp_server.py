"""MCP Server domain - configuration for MCP server connections."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ..ids import MCPServerId


@dataclass
class MCPServer:
    """An MCP server registration.

    Core fields cover universal MCP server properties. The approval model
    unifies episteme's server-level approval and lumina's tool-level approval:

        approval_mode: Server-level default - "manual" or "auto"
        auto_approve_tools: Tool-level exceptions that skip approval

    The settings dict holds consumer-specific configuration:
        - Episteme: timeout_ms, max_retries
        - Lumina: (future consumer-specific config)
    """

    id: MCPServerId
    name: str
    url: str
    enabled: bool = True
    headers: Optional[dict[str, str]] = None
    approval_mode: str = "manual"
    auto_approve_tools: list[str] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
