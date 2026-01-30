"""Content layer abstract stores - BlobStore, ContentStore, AssetStore."""

from abc import ABC, abstractmethod
from typing import Optional

from ..ids import AssetId, ContentBlockId, EntityId
from ..types import ContentOrigin
from .stored import AssetRef, ContentBlock, StoredContent


class BlobStore(ABC):
    """Abstract content-addressable blob storage.

    Handles raw binary data with SHA-256 deduplication.
    Implementations may use the local filesystem, S3, GCS, etc.
    """

    @abstractmethod
    async def store(self, data: bytes, mime_type: str) -> tuple[str, str]:
        """Store blob data, returning (content_hash, relative_path).

        Deduplicates: identical content produces the same hash and is stored once.
        """
        ...

    @abstractmethod
    async def retrieve(self, relative_path: str) -> Optional[bytes]:
        """Retrieve blob data by relative path. Returns None if missing."""
        ...

    @abstractmethod
    async def retrieve_by_hash(self, content_hash: str, mime_type: str) -> Optional[bytes]:
        """Retrieve blob data by content hash."""
        ...

    @abstractmethod
    async def exists(self, content_hash: str, mime_type: str) -> bool:
        """Check if a blob exists in storage."""
        ...

    @abstractmethod
    async def delete(self, relative_path: str) -> bool:
        """Delete a blob. Returns True if deleted."""
        ...


class ContentStore(ABC):
    """Abstract store for immutable text content blocks."""

    @abstractmethod
    async def store_text(
        self,
        text: str,
        origin: ContentOrigin,
        model_id: Optional[str] = None,
    ) -> ContentBlockId: ...

    @abstractmethod
    async def get_text(self, content_block_id: ContentBlockId) -> Optional[str]: ...

    @abstractmethod
    async def get_content_block(
        self,
        content_block_id: ContentBlockId,
    ) -> Optional[ContentBlock]: ...

    @abstractmethod
    async def resolve_content(
        self,
        refs: list[StoredContent],
    ) -> list[ContentBlock]: ...


class AssetStore(ABC):
    """Abstract store for binary assets (images, audio, files)."""

    @abstractmethod
    async def store_asset(
        self,
        entity_id: EntityId,
        data: bytes,
        mime_type: str,
        original_filename: Optional[str] = None,
    ) -> AssetRef: ...

    @abstractmethod
    async def get_asset_data(self, asset_id: AssetId) -> Optional[bytes]: ...

    @abstractmethod
    async def get_asset_metadata(
        self,
        asset_id: AssetId,
    ) -> Optional[dict]: ...

    @abstractmethod
    async def delete_asset(self, asset_id: AssetId) -> bool: ...
