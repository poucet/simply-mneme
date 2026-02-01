"""SQLite implementation of AssetStore."""

from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..content.blob_storage import BlobStorage
from ..content.protocol import AssetStore
from ..content.stored import AssetRef
from ..ids import AssetId, EntityId
from ..types import EntityType
from .models import AssetModel, EntityModel, epoch_ms_to_datetime


class SqliteAssetStore(AssetStore):
    """SQLite-backed AssetStore implementation.

    Stores asset metadata in the database and delegates binary data
    to a content-addressable BlobStorage.
    """

    def __init__(self, db: AsyncSession, blob_storage: BlobStorage) -> None:
        self.db = db
        self.blob_storage = blob_storage

    async def store_asset(
        self,
        entity_id: EntityId,
        data: bytes,
        mime_type: str,
        original_filename: Optional[str] = None,
    ) -> AssetRef:
        # Store blob (deduplicates by content hash)
        blob_hash, _relative_path = await self.blob_storage.store(data, mime_type)

        # Create entity for the asset
        entity_row = EntityModel(
            id=str(entity_id),
            entity_type=EntityType.ASSET.value,
            name=original_filename,
        )
        self.db.add(entity_row)
        await self.db.flush()

        # Create asset record
        asset_row = AssetModel(
            id=str(entity_id),
            blob_hash=blob_hash,
            mime_type=mime_type,
            size_bytes=len(data),
            is_private=False,
        )
        self.db.add(asset_row)
        await self.db.flush()

        return AssetRef(asset_id=AssetId(str(entity_id)), mime_type=mime_type)

    async def get_asset_data(self, asset_id: AssetId) -> Optional[bytes]:
        result = await self.db.execute(
            select(AssetModel).where(AssetModel.id == str(asset_id))
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None

        # Derive path from hash + mime_type (content-addressable)
        return await self.blob_storage.retrieve_by_hash(row.blob_hash, row.mime_type)

    async def get_asset_metadata(self, asset_id: AssetId) -> Optional[dict]:
        result = await self.db.execute(
            select(AssetModel, EntityModel)
            .outerjoin(EntityModel, AssetModel.id == EntityModel.id)
            .where(AssetModel.id == str(asset_id))
        )
        row = result.one_or_none()
        if row is None:
            return None
        asset_row, entity_row = row

        return {
            "id": asset_row.id,
            "mime_type": asset_row.mime_type,
            "blob_hash": asset_row.blob_hash,
            "size_bytes": asset_row.size_bytes,
            "file_size": asset_row.size_bytes,  # backward compat alias
            "is_private": asset_row.is_private,
            "original_filename": entity_row.name if entity_row else None,
            "created_at": epoch_ms_to_datetime(asset_row.created_at),
        }

    async def delete_asset(self, asset_id: AssetId) -> bool:
        # Delete from DB (cascade will remove entity too)
        result = await self.db.execute(
            delete(EntityModel).where(EntityModel.id == str(asset_id))
        )
        await self.db.flush()
        return result.rowcount > 0
