"""SQLite implementation of AssetStore."""

import hashlib
from pathlib import Path
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..content.protocol import AssetStore
from ..content.stored import AssetRef
from ..ids import AssetId, EntityId
from ..types import EntityType
from .models import AssetModel, EntityModel, epoch_ms_to_datetime, new_uuid


class SqliteAssetStore(AssetStore):
    """SQLite-backed AssetStore implementation.

    Stores asset metadata in the database and binary data on the filesystem
    using content-addressable sharded paths (first 2 chars of SHA-256 hash).
    """

    def __init__(self, db: AsyncSession, storage_root: Path) -> None:
        self.db = db
        self.storage_root = storage_root
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def _blob_path(self, content_hash: str) -> Path:
        """Get the sharded filesystem path for a content hash."""
        shard = content_hash[:2]
        return self.storage_root / shard / content_hash

    async def store_asset(
        self,
        entity_id: EntityId,
        data: bytes,
        mime_type: str,
        original_filename: Optional[str] = None,
    ) -> AssetRef:
        content_hash = hashlib.sha256(data).hexdigest()

        # Write blob to filesystem (deduplicated by hash)
        blob_path = self._blob_path(content_hash)
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        if not blob_path.exists():
            blob_path.write_bytes(data)

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
            storage_path=str(blob_path),
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

        blob_path = Path(row.storage_path)
        if not blob_path.exists():
            return None
        return blob_path.read_bytes()

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
