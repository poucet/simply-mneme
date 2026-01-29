"""Entity domain - the addressable identity layer.

Every conversation, document, and asset is an Entity first.
This provides unified identity, naming, privacy, and archival.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ..ids import EntityId, UserId
from ..types import EntityType, RelationType


@dataclass
class Entity:
    """An addressable entity in the UCM."""

    id: EntityId
    type: EntityType
    user_id: Optional[UserId] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    is_private: bool = False
    is_archived: bool = False
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EntityRelation:
    """A directed relationship between two entities."""

    from_entity_id: EntityId
    to_entity_id: EntityId
    relation_type: RelationType
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
