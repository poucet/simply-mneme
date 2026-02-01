"""SQLite implementation of ContentStore."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import hashlib

from ..content.protocol import ContentStore
from ..ids import ContentBlockId
from ..types import ContentOrigin
from ..content.stored import ContentBlock, StoredContent, TextRef
from .models import ContentBlockModel, epoch_ms_to_datetime, new_uuid


class SqliteContentStore(ContentStore):
    """SQLite-backed ContentStore implementation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _to_domain(self, row: ContentBlockModel) -> ContentBlock:
        return ContentBlock(
            id=ContentBlockId(row.id),
            text=row.text,
            origin=ContentOrigin(row.origin_kind),
            model_id=row.origin_model_id,
            created_at=epoch_ms_to_datetime(row.created_at),
        )

    async def store_text(
        self,
        text: str,
        origin: ContentOrigin,
        model_id: Optional[str] = None,
    ) -> ContentBlockId:
        block_id = new_uuid()
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        row = ContentBlockModel(
            id=block_id,
            content_hash=content_hash,
            content_type="plain",
            text=text,
            is_private=False,
            origin_kind=origin.value,
            origin_model_id=model_id,
        )
        self.db.add(row)
        await self.db.flush()
        return ContentBlockId(block_id)

    async def get_text(self, content_block_id: ContentBlockId) -> Optional[str]:
        result = await self.db.execute(
            select(ContentBlockModel.text).where(
                ContentBlockModel.id == str(content_block_id)
            )
        )
        return result.scalar_one_or_none()

    async def get_content_block(
        self,
        content_block_id: ContentBlockId,
    ) -> Optional[ContentBlock]:
        result = await self.db.execute(
            select(ContentBlockModel).where(
                ContentBlockModel.id == str(content_block_id)
            )
        )
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def resolve_content(
        self,
        refs: list[StoredContent],
    ) -> list[ContentBlock]:
        """Resolve TextRef items to full ContentBlock objects.

        Only TextRef items are resolved; other content types are skipped.
        """
        text_ids = [
            str(ref.content_block_id)
            for ref in refs
            if isinstance(ref, TextRef)
        ]
        if not text_ids:
            return []

        result = await self.db.execute(
            select(ContentBlockModel).where(ContentBlockModel.id.in_(text_ids))
        )
        rows_by_id = {row.id: row for row in result.scalars()}

        # Return in the same order as the input refs
        blocks = []
        for ref in refs:
            if isinstance(ref, TextRef):
                row = rows_by_id.get(str(ref.content_block_id))
                if row:
                    blocks.append(self._to_domain(row))
        return blocks
