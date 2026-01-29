"""Content layer abstract stores - ContentStore, AssetStore."""

from abc import ABC, abstractmethod
from typing import Optional

from ..ids import AssetId, ContentBlockId, EntityId
from ..types import ContentOrigin
from .stored import ContentBlock, StoredContent


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
    ) -> AssetId: ...

    @abstractmethod
    async def get_asset_data(self, asset_id: AssetId) -> Optional[bytes]: ...

    @abstractmethod
    async def get_asset_metadata(
        self,
        asset_id: AssetId,
    ) -> Optional[dict]: ...

    @abstractmethod
    async def delete_asset(self, asset_id: AssetId) -> bool: ...
