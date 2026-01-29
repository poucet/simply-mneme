"""User domain."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..ids import UserId


@dataclass
class User:
    """A user in the system."""

    id: UserId
    email: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
