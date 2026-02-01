"""OAuth connection domain - credentials for external OAuth providers."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ..ids import OAuthConnectionId, UserId


@dataclass
class OAuthConnection:
    """An OAuth connection to an external provider (Google, Anthropic, etc.).

    Stores credentials and metadata for a user's connection to an OAuth provider.
    Shared across consumers (episteme, lumina) via mneme.
    """

    id: OAuthConnectionId
    user_id: UserId
    provider: str  # 'google', 'anthropic', etc.
    access_token: str
    scopes: list[str] = field(default_factory=list)
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    provider_user_id: Optional[str] = None
    provider_email: Optional[str] = None
    connection_name: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: Optional[datetime] = None

    def is_token_expired(self) -> bool:
        """Check if the access token is expired."""
        if not self.token_expires_at:
            return False
        return datetime.now(timezone.utc) >= self.token_expires_at

    def has_scope(self, scope: str) -> bool:
        """Check if this connection has a specific scope."""
        return scope in self.scopes

    def has_all_scopes(self, required_scopes: list[str]) -> bool:
        """Check if this connection has all required scopes."""
        return all(scope in self.scopes for scope in required_scopes)
