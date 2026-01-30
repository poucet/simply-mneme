"""Document domain - Document/Tab/Revision structure.

Documents use a Document→Tab→Revision hierarchy:
- Document: a top-level entity with source tracking
- Tab: a section within a document (supports nesting via parent_tab_id)
- Revision: an immutable snapshot of a tab's content
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..ids import AssetId, DocumentId, RevisionId, TabId, UserId
from ..types import DocumentSource
from ..addressable.entity import Entity


@dataclass
class Document:
    """A document entity with source tracking."""

    entity: Entity
    source: DocumentSource
    source_id: Optional[str] = None

    @property
    def id(self) -> DocumentId:
        return self.entity.id


@dataclass
class Tab:
    """A tab within a document."""

    id: TabId
    document_id: DocumentId
    tab_index: int = 0
    title: str = ""
    parent_tab_id: Optional[TabId] = None
    icon: Optional[str] = None
    content_markdown: Optional[str] = None
    referenced_assets: list[AssetId] = field(default_factory=list)
    source_tab_id: Optional[str] = None
    current_revision_id: Optional[RevisionId] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Revision:
    """An immutable revision of a tab's content."""

    id: RevisionId
    tab_id: TabId
    revision_number: int
    content_markdown: str
    content_hash: str
    created_by: UserId
    parent_revision_id: Optional[RevisionId] = None
    referenced_assets: list[AssetId] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
