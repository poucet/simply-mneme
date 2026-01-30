"""mneme - Storage layer implementing noema's Unified Content Model (UCM).

Three-layer architecture:
  Addressable: Entity identity (Entity, EntityRelation)
  Structure:   Domain organization (Conversation, Turn, Span, Message, Document, Tab, Revision, User)
  Content:     Immutable storage (StoredContent, ContentBlock)
"""

from .ids import (
    AssetId,
    ContentBlockId,
    ConversationId,
    DocumentId,
    EntityId,
    MessageId,
    RevisionId,
    SpanId,
    TabId,
    TurnId,
    UserId,
)
from .types import (
    ContentOrigin,
    DocumentSource,
    EntityType,
    RelationType,
    Role,
)

from .addressable import Entity, EntityRelation, EntityStore
from .structure import (
    Conversation,
    ConversationStore,
    Document,
    DocumentStore,
    Message,
    MessageWithContent,
    Revision,
    Span,
    Tab,
    Turn,
    TurnWithContent,
    User,
    UserStore,
)
from .content import (
    AssetRef,
    AssetStore,
    BlobStore,
    ContentBlock,
    ContentStore,
    DocumentRef,
    StoredContent,
    TextRef,
    ToolCall,
    ToolResult,
)

__all__ = [
    # IDs
    "EntityId",
    "ConversationId",
    "TurnId",
    "SpanId",
    "MessageId",
    "ContentBlockId",
    "AssetId",
    "DocumentId",
    "TabId",
    "RevisionId",
    "UserId",
    # Enums
    "EntityType",
    "Role",
    "RelationType",
    "ContentOrigin",
    "DocumentSource",
    # Addressable layer
    "Entity",
    "EntityRelation",
    "EntityStore",
    # Structure layer
    "Conversation",
    "Turn",
    "Span",
    "Message",
    "MessageWithContent",
    "TurnWithContent",
    "Document",
    "Tab",
    "Revision",
    "User",
    # Content layer
    "StoredContent",
    "TextRef",
    "AssetRef",
    "DocumentRef",
    "ToolCall",
    "ToolResult",
    "ContentBlock",
    # Stores
    "BlobStore",
    "ConversationStore",
    "DocumentStore",
    "UserStore",
    "ContentStore",
    "AssetStore",
]
