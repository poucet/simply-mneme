"""SQLite implementation of EntityStore."""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..addressable.protocol import EntityStore
from ..ids import EntityId, UserId
from ..types import EntityType, RelationType
from ..addressable.entity import Entity, EntityRelation
from .models import (
    EntityModel,
    EntityRelationModel,
    epoch_ms_to_datetime,
    datetime_to_epoch_ms,
    new_uuid,
    now_epoch_ms,
    parse_uuid,
)


class SqliteEntityStore(EntityStore):
    """SQLite-backed EntityStore implementation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- Conversion helpers --

    def _to_domain(self, row: EntityModel) -> Entity:
        return Entity(
            id=EntityId(row.id),
            type=EntityType(row.type),
            user_id=parse_uuid(row.user_id),
            name=row.name,
            slug=row.slug,
            is_private=row.is_private,
            is_archived=row.is_archived,
            metadata=row.metadata_,
            created_at=epoch_ms_to_datetime(row.created_at),
            updated_at=epoch_ms_to_datetime(row.updated_at),
        )

    def _relation_to_domain(self, row: EntityRelationModel) -> EntityRelation:
        return EntityRelation(
            from_entity_id=EntityId(row.from_entity_id),
            to_entity_id=EntityId(row.to_entity_id),
            relation_type=RelationType(row.relation_type),
            metadata=row.metadata_,
            created_at=epoch_ms_to_datetime(row.created_at),
        )

    # -- CRUD --

    async def create_entity(
        self,
        entity_type: EntityType,
        user_id: Optional[UserId] = None,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        is_private: bool = False,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Entity:
        row = EntityModel(
            id=new_uuid(),
            type=entity_type.value,
            user_id=str(user_id) if user_id else None,
            name=name,
            slug=slug,
            is_private=is_private,
            metadata_=metadata,
        )
        self.db.add(row)
        await self.db.flush()
        return self._to_domain(row)

    async def get_entity(self, entity_id: EntityId) -> Optional[Entity]:
        result = await self.db.execute(
            select(EntityModel).where(EntityModel.id == str(entity_id))
        )
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def get_entity_by_slug(self, slug: str) -> Optional[Entity]:
        result = await self.db.execute(
            select(EntityModel).where(EntityModel.slug == slug)
        )
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list_entities(
        self,
        user_id: UserId,
        entity_type: Optional[EntityType] = None,
    ) -> list[Entity]:
        stmt = select(EntityModel).where(
            EntityModel.user_id == str(user_id),
            EntityModel.is_archived == False,
        )
        if entity_type is not None:
            stmt = stmt.where(EntityModel.type == entity_type.value)
        stmt = stmt.order_by(EntityModel.updated_at.desc())

        result = await self.db.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def update_entity(
        self,
        entity_id: EntityId,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        is_private: Optional[bool] = None,
        is_archived: Optional[bool] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Entity:
        result = await self.db.execute(
            select(EntityModel).where(EntityModel.id == str(entity_id))
        )
        row = result.scalar_one()

        if name is not None:
            row.name = name
        if slug is not None:
            row.slug = slug
        if is_private is not None:
            row.is_private = is_private
        if is_archived is not None:
            row.is_archived = is_archived
        if metadata is not None:
            row.metadata_ = metadata

        row.updated_at = now_epoch_ms()
        await self.db.flush()
        return self._to_domain(row)

    async def archive_entity(self, entity_id: EntityId) -> None:
        result = await self.db.execute(
            select(EntityModel).where(EntityModel.id == str(entity_id))
        )
        row = result.scalar_one()
        row.is_archived = True
        row.updated_at = now_epoch_ms()
        await self.db.flush()

    async def delete_entity(self, entity_id: EntityId) -> None:
        await self.db.execute(
            delete(EntityModel).where(EntityModel.id == str(entity_id))
        )
        await self.db.flush()

    # -- Relations --

    async def add_relation(
        self,
        from_id: EntityId,
        to_id: EntityId,
        relation_type: RelationType,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        row = EntityRelationModel(
            id=new_uuid(),
            from_entity_id=str(from_id),
            to_entity_id=str(to_id),
            relation_type=relation_type.value,
            metadata_=metadata,
        )
        self.db.add(row)
        await self.db.flush()

    async def get_relations_from(
        self,
        entity_id: EntityId,
        relation_type: Optional[RelationType] = None,
    ) -> list[tuple[EntityId, EntityRelation]]:
        stmt = select(EntityRelationModel).where(
            EntityRelationModel.from_entity_id == str(entity_id)
        )
        if relation_type is not None:
            stmt = stmt.where(EntityRelationModel.relation_type == relation_type.value)

        result = await self.db.execute(stmt)
        return [
            (EntityId(row.to_entity_id), self._relation_to_domain(row))
            for row in result.scalars()
        ]

    async def get_relations_to(
        self,
        entity_id: EntityId,
        relation_type: Optional[RelationType] = None,
    ) -> list[tuple[EntityId, EntityRelation]]:
        stmt = select(EntityRelationModel).where(
            EntityRelationModel.to_entity_id == str(entity_id)
        )
        if relation_type is not None:
            stmt = stmt.where(EntityRelationModel.relation_type == relation_type.value)

        result = await self.db.execute(stmt)
        return [
            (EntityId(row.from_entity_id), self._relation_to_domain(row))
            for row in result.scalars()
        ]

    async def remove_relation(
        self,
        from_id: EntityId,
        to_id: EntityId,
        relation_type: RelationType,
    ) -> None:
        await self.db.execute(
            delete(EntityRelationModel).where(
                EntityRelationModel.from_entity_id == str(from_id),
                EntityRelationModel.to_entity_id == str(to_id),
                EntityRelationModel.relation_type == relation_type.value,
            )
        )
        await self.db.flush()
