"""Stored content types - the immutable content layer.

Content is stored separately from messages and referenced via StoredContent.
This enables deduplication, immutable audit trails, and content-addressable storage.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Union

from ..ids import AssetId, ContentBlockId, DocumentId
from ..types import ContentOrigin


@dataclass(frozen=True)
class TextRef:
    """Reference to an immutable text content block."""

    content_block_id: ContentBlockId


@dataclass(frozen=True)
class AssetRef:
    """Reference to a stored asset (image, audio, file)."""

    asset_id: AssetId
    mime_type: str


@dataclass(frozen=True)
class DocumentRef:
    """Reference to a document entity (for RAG injection)."""

    document_id: DocumentId


@dataclass(frozen=True)
class ToolCall:
    """A tool/function call request."""

    id: str
    name: str
    input: dict[str, Any]


# Content types that can appear inside tool results (no recursion).
ToolContent = Union[TextRef, AssetRef]


@dataclass(frozen=True)
class ToolResult:
    """Result of a tool/function call."""

    tool_call_id: str
    content: tuple[ToolContent, ...] = ()
    is_error: bool = False


StoredContent = Union[TextRef, AssetRef, DocumentRef, ToolCall, ToolResult]


@dataclass
class ContentBlock:
    """An immutable text content block with origin tracking."""

    id: ContentBlockId
    text: str
    origin: ContentOrigin
    model_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
