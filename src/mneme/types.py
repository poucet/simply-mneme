"""Core enumerations for the UCM domain model."""

from enum import Enum


class EntityType(str, Enum):
    """Types of addressable entities in the UCM."""
    CONVERSATION = "conversation"
    DOCUMENT = "document"
    ASSET = "asset"


class Role(str, Enum):
    """Message roles in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class RelationType(str, Enum):
    """Types of relationships between entities."""
    FORKED_FROM = "forked_from"
    REFERENCES = "references"
    DERIVED_FROM = "derived_from"
    GROUPED_WITH = "grouped_with"


class ContentOrigin(str, Enum):
    """Origin of a content block - who/what produced it."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    IMPORT = "import"


class DocumentSource(str, Enum):
    """Source of a document."""
    GOOGLE_DRIVE = "google_drive"
    AI_GENERATED = "ai_generated"
    USER_CREATED = "user_created"
