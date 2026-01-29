"""EntityStore - abstract storage interface for the addressable layer."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from ..ids import EntityId, UserId
from ..types import EntityType, RelationType
from .entity import Entity, EntityRelation


class EntityStore(ABC):
    """Abstract store for entity CRUD and relations."""

    # -- CRUD --

    @abstractmethod
    async def create_entity(
        self,
        entity_type: EntityType,
        user_id: Optional[UserId] = None,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        is_private: bool = False,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Entity: ...

    @abstractmethod
    async def get_entity(self, entity_id: EntityId) -> Optional[Entity]: ...

    @abstractmethod
    async def get_entity_by_slug(self, slug: str) -> Optional[Entity]: ...

    @abstractmethod
    async def list_entities(
        self,
        user_id: UserId,
        entity_type: Optional[EntityType] = None,
    ) -> list[Entity]: ...

    @abstractmethod
    async def update_entity(
        self,
        entity_id: EntityId,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        is_private: Optional[bool] = None,
        is_archived: Optional[bool] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Entity: ...

    @abstractmethod
    async def archive_entity(self, entity_id: EntityId) -> None: ...

    @abstractmethod
    async def delete_entity(self, entity_id: EntityId) -> None: ...

    # -- Relations --

    @abstractmethod
    async def add_relation(
        self,
        from_id: EntityId,
        to_id: EntityId,
        relation_type: RelationType,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None: ...

    @abstractmethod
    async def get_relations_from(
        self,
        entity_id: EntityId,
        relation_type: Optional[RelationType] = None,
    ) -> list[tuple[EntityId, EntityRelation]]: ...

    @abstractmethod
    async def get_relations_to(
        self,
        entity_id: EntityId,
        relation_type: Optional[RelationType] = None,
    ) -> list[tuple[EntityId, EntityRelation]]: ...

    @abstractmethod
    async def remove_relation(
        self,
        from_id: EntityId,
        to_id: EntityId,
        relation_type: RelationType,
    ) -> None: ...
