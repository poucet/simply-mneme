"""SQLite implementation of DocumentStore."""

from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..structure.protocol import DocumentStore
from ..ids import AssetId, DocumentId, MessageId, RevisionId, TabId, UserId
from ..types import DocumentSource, EntityType
from ..addressable.entity import Entity
from ..structure.document import Document, Revision, Tab
from .models import (
    DocumentModel,
    EntityModel,
    RevisionModel,
    TabModel,
    epoch_ms_to_datetime,
    new_uuid,
    now_epoch_ms,
    parse_uuid,
)


class SqliteDocumentStore(DocumentStore):
    """SQLite-backed DocumentStore implementation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- Conversion helpers --

    def _entity_to_domain(self, row: EntityModel) -> Entity:
        from .entity_store import SqliteEntityStore
        return SqliteEntityStore(self.db)._to_domain(row)

    def _document_to_domain(self, doc_row: DocumentModel, entity_row: EntityModel) -> Document:
        return Document(
            entity=self._entity_to_domain(entity_row),
            source=DocumentSource(doc_row.source),
            source_id=doc_row.source_id,
        )

    def _tab_to_domain(self, row: TabModel) -> Tab:
        return Tab(
            id=parse_uuid(row.id),
            document_id=DocumentId(row.document_id),
            tab_index=row.tab_index,
            title=row.title,
            parent_tab_id=parse_uuid(row.parent_tab_id),
            icon=row.icon,
            content_markdown=row.content_markdown,
            referenced_assets=[AssetId(a) for a in (row.referenced_assets or [])],
            source_tab_id=row.source_tab_id,
            current_revision_id=parse_uuid(row.current_revision_id),
            created_at=epoch_ms_to_datetime(row.created_at),
            updated_at=epoch_ms_to_datetime(row.updated_at),
        )

    def _revision_to_domain(self, row: RevisionModel) -> Revision:
        return Revision(
            id=parse_uuid(row.id),
            tab_id=parse_uuid(row.tab_id),
            revision_number=row.revision_number,
            content_markdown=row.content_markdown,
            content_hash=row.content_hash,
            created_by=parse_uuid(row.created_by),
            parent_revision_id=parse_uuid(row.parent_revision_id),
            referenced_assets=[AssetId(a) for a in (row.referenced_assets or [])],
            created_at=epoch_ms_to_datetime(row.created_at),
        )

    # -- Document CRUD --

    async def create_document(
        self,
        user_id: UserId,
        title: str,
        source: DocumentSource,
        source_id: Optional[str] = None,
    ) -> Document:
        entity_id = new_uuid()
        entity_row = EntityModel(
            id=entity_id,
            entity_type=EntityType.DOCUMENT.value,
            user_id=str(user_id),
            name=title,
        )
        self.db.add(entity_row)
        await self.db.flush()

        doc_row = DocumentModel(
            id=entity_id,
            user_id=str(user_id),
            title=title,
            source=source.value,
            source_id=source_id,
        )
        self.db.add(doc_row)
        await self.db.flush()

        return self._document_to_domain(doc_row, entity_row)

    async def get_document(self, document_id: DocumentId) -> Optional[Document]:
        result = await self.db.execute(
            select(DocumentModel, EntityModel)
            .join(EntityModel, DocumentModel.id == EntityModel.id)
            .where(DocumentModel.id == str(document_id))
        )
        row = result.one_or_none()
        if row is None:
            return None
        doc_row, entity_row = row
        return self._document_to_domain(doc_row, entity_row)

    async def get_document_by_source(
        self,
        user_id: UserId,
        source: DocumentSource,
        source_id: str,
    ) -> Optional[Document]:
        result = await self.db.execute(
            select(DocumentModel, EntityModel)
            .join(EntityModel, DocumentModel.id == EntityModel.id)
            .where(
                EntityModel.user_id == str(user_id),
                DocumentModel.source == source.value,
                DocumentModel.source_id == source_id,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        doc_row, entity_row = row
        return self._document_to_domain(doc_row, entity_row)

    async def list_documents(
        self,
        user_id: UserId,
        source: Optional[DocumentSource] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Document]:
        query = (
            select(DocumentModel, EntityModel)
            .join(EntityModel, DocumentModel.id == EntityModel.id)
            .where(
                EntityModel.user_id == str(user_id),
                EntityModel.is_archived == False,
            )
            .order_by(EntityModel.updated_at.desc())
        )
        if source is not None:
            query = query.where(DocumentModel.source == source.value)
        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return [self._document_to_domain(d, e) for d, e in result]

    async def search_documents(
        self,
        user_id: UserId,
        query: str,
        limit: int = 20,
    ) -> list[Document]:
        result = await self.db.execute(
            select(DocumentModel, EntityModel)
            .join(EntityModel, DocumentModel.id == EntityModel.id)
            .where(
                EntityModel.user_id == str(user_id),
                EntityModel.is_archived == False,
                EntityModel.name.ilike(f"%{query}%"),
            )
            .order_by(EntityModel.updated_at.desc())
            .limit(limit)
        )
        return [self._document_to_domain(d, e) for d, e in result]

    async def update_document_title(
        self,
        document_id: DocumentId,
        title: str,
    ) -> None:
        result = await self.db.execute(
            select(EntityModel).where(EntityModel.id == str(document_id))
        )
        entity_row = result.scalar_one()
        entity_row.name = title
        entity_row.updated_at = now_epoch_ms()
        await self.db.flush()

    async def delete_document(self, document_id: DocumentId) -> bool:
        result = await self.db.execute(
            delete(EntityModel).where(EntityModel.id == str(document_id))
        )
        await self.db.flush()
        return result.rowcount > 0

    # -- Tab CRUD --

    async def create_tab(
        self,
        document_id: DocumentId,
        title: str,
        tab_index: int = 0,
        parent_tab_id: Optional[TabId] = None,
        icon: Optional[str] = None,
        content_markdown: Optional[str] = None,
        referenced_assets: Optional[list[AssetId]] = None,
        source_tab_id: Optional[str] = None,
    ) -> Tab:
        row = TabModel(
            id=new_uuid(),
            document_id=str(document_id),
            tab_index=tab_index,
            title=title,
            parent_tab_id=str(parent_tab_id) if parent_tab_id else None,
            icon=icon,
            content_markdown=content_markdown,
            referenced_assets=[str(a) for a in (referenced_assets or [])],
            source_tab_id=source_tab_id,
        )
        self.db.add(row)
        await self.db.flush()
        return self._tab_to_domain(row)

    async def get_tab(self, tab_id: TabId) -> Optional[Tab]:
        result = await self.db.execute(
            select(TabModel).where(TabModel.id == str(tab_id))
        )
        row = result.scalar_one_or_none()
        return self._tab_to_domain(row) if row else None

    async def list_tabs(self, document_id: DocumentId) -> list[Tab]:
        result = await self.db.execute(
            select(TabModel)
            .where(TabModel.document_id == str(document_id))
            .order_by(TabModel.tab_index)
        )
        return [self._tab_to_domain(row) for row in result.scalars()]

    async def get_tab_by_source_id(
        self,
        document_id: DocumentId,
        source_tab_id: str,
    ) -> Optional[Tab]:
        result = await self.db.execute(
            select(TabModel).where(
                TabModel.document_id == str(document_id),
                TabModel.source_tab_id == source_tab_id,
            )
        )
        row = result.scalar_one_or_none()
        return self._tab_to_domain(row) if row else None

    async def get_child_tabs(self, parent_tab_id: TabId) -> list[Tab]:
        result = await self.db.execute(
            select(TabModel)
            .where(TabModel.parent_tab_id == str(parent_tab_id))
            .order_by(TabModel.tab_index)
        )
        return [self._tab_to_domain(row) for row in result.scalars()]

    async def update_tab(
        self,
        tab_id: TabId,
        title: Optional[str] = None,
        icon: Optional[str] = None,
        content_markdown: Optional[str] = None,
        referenced_assets: Optional[list[AssetId]] = None,
        tab_index: Optional[int] = None,
        parent_tab_id: Optional[TabId] = None,
    ) -> Tab:
        result = await self.db.execute(
            select(TabModel).where(TabModel.id == str(tab_id))
        )
        row = result.scalar_one()
        if title is not None:
            row.title = title
        if icon is not None:
            row.icon = icon
        if content_markdown is not None:
            row.content_markdown = content_markdown
        if referenced_assets is not None:
            row.referenced_assets = [str(a) for a in referenced_assets]
        if tab_index is not None:
            row.tab_index = tab_index
        if parent_tab_id is not None:
            row.parent_tab_id = str(parent_tab_id)
        row.updated_at = now_epoch_ms()
        await self.db.flush()
        return self._tab_to_domain(row)

    async def update_tab_content(
        self,
        tab_id: TabId,
        content_markdown: str,
        referenced_assets: Optional[list[AssetId]] = None,
    ) -> None:
        result = await self.db.execute(
            select(TabModel).where(TabModel.id == str(tab_id))
        )
        row = result.scalar_one()
        row.content_markdown = content_markdown
        if referenced_assets is not None:
            row.referenced_assets = [str(a) for a in referenced_assets]
        row.updated_at = now_epoch_ms()
        await self.db.flush()

    async def delete_tabs(self, document_id: DocumentId) -> int:
        result = await self.db.execute(
            delete(TabModel).where(TabModel.document_id == str(document_id))
        )
        await self.db.flush()
        return result.rowcount

    async def set_tab_revision(
        self,
        tab_id: TabId,
        revision_id: RevisionId,
    ) -> None:
        result = await self.db.execute(
            select(TabModel).where(TabModel.id == str(tab_id))
        )
        row = result.scalar_one()
        row.current_revision_id = str(revision_id)
        row.updated_at = now_epoch_ms()
        await self.db.flush()

    async def delete_tab(self, tab_id: TabId) -> bool:
        result = await self.db.execute(
            delete(TabModel).where(TabModel.id == str(tab_id))
        )
        await self.db.flush()
        return result.rowcount > 0

    # -- Revision CRUD --

    async def create_revision(
        self,
        tab_id: TabId,
        content_markdown: str,
        content_hash: str,
        created_by: UserId,
        referenced_assets: Optional[list[AssetId]] = None,
    ) -> Revision:
        # Get next revision number
        result = await self.db.execute(
            select(TabModel).where(TabModel.id == str(tab_id))
        )
        tab_row = result.scalar_one()
        parent_revision_id = tab_row.current_revision_id

        # Count existing revisions for numbering
        from sqlalchemy import func
        count_result = await self.db.execute(
            select(func.count()).select_from(RevisionModel).where(
                RevisionModel.tab_id == str(tab_id)
            )
        )
        revision_number = count_result.scalar() + 1

        row = RevisionModel(
            id=new_uuid(),
            tab_id=str(tab_id),
            revision_number=revision_number,
            parent_revision_id=parent_revision_id,
            content_markdown=content_markdown,
            content_hash=content_hash,
            referenced_assets=[str(a) for a in (referenced_assets or [])],
            created_by=str(created_by),
        )
        self.db.add(row)

        # Update tab to point to this revision
        tab_row.current_revision_id = row.id
        tab_row.content_markdown = content_markdown
        tab_row.updated_at = now_epoch_ms()

        await self.db.flush()
        return self._revision_to_domain(row)

    async def get_revision(self, revision_id: RevisionId) -> Optional[Revision]:
        result = await self.db.execute(
            select(RevisionModel).where(RevisionModel.id == str(revision_id))
        )
        row = result.scalar_one_or_none()
        return self._revision_to_domain(row) if row else None

    async def list_revisions(self, tab_id: TabId) -> list[Revision]:
        result = await self.db.execute(
            select(RevisionModel)
            .where(RevisionModel.tab_id == str(tab_id))
            .order_by(RevisionModel.revision_number)
        )
        return [self._revision_to_domain(row) for row in result.scalars()]

    async def promote_from_message(
        self,
        message_id: MessageId,
        user_id: UserId,
        title: Optional[str] = None,
    ) -> Document:
        # This is a complex operation that creates a document from a message's content.
        # For now, create an empty document - the caller populates content.
        doc = await self.create_document(
            user_id=user_id,
            title=title or "Untitled Document",
            source=DocumentSource.AI_GENERATED,
        )
        return doc
