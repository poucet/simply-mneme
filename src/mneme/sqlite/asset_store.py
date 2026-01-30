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
        content_hash, relative_path = await self.blob_storage.store(data, mime_type)

        # Create entity for the asset
        entity_row = EntityModel(
            id=str(entity_id),
            type=EntityType.ASSET.value,
            name=original_filename,
        )
        self.db.add(entity_row)
        await self.db.flush()

        # Create asset record
        asset_row = AssetModel(
            id=str(entity_id),
            mime_type=mime_type,
            content_hash=content_hash,
            file_size=len(data),
            original_filename=original_filename,
            storage_path=relative_path,
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

        return await self.blob_storage.retrieve(row.storage_path)

    async def get_asset_metadata(self, asset_id: AssetId) -> Optional[dict]:
        result = await self.db.execute(
            select(AssetModel).where(AssetModel.id == str(asset_id))
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None

        return {
            "id": row.id,
            "mime_type": row.mime_type,
            "content_hash": row.content_hash,
            "file_size": row.file_size,
            "original_filename": row.original_filename,
            "created_at": epoch_ms_to_datetime(row.created_at),
        }

    async def delete_asset(self, asset_id: AssetId) -> bool:
        # Delete from DB (cascade will remove entity too)
        result = await self.db.execute(
            delete(EntityModel).where(EntityModel.id == str(asset_id))
        )
        await self.db.flush()
        return result.rowcount > 0
