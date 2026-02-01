"""Type-safe UUID identifiers for UCM domain objects.

Each domain concept gets its own ID type to prevent mixing IDs
across unrelated entities (e.g. passing a TurnId where a SpanId is expected).

Mirrors noema's id.rs approach but uses Python's UUID as the base.
"""

from uuid import UUID, uuid4


class EntityId(UUID):
    """Identity for any addressable entity (conversation, document, asset)."""

    @classmethod
    def generate(cls) -> 'EntityId':
        return cls(int=uuid4().int)


class TurnId(UUID):
    """Identity for a turn (shared position in a conversation)."""

    @classmethod
    def generate(cls) -> 'TurnId':
        return cls(int=uuid4().int)


class SpanId(UUID):
    """Identity for a span (one alternative at a turn)."""

    @classmethod
    def generate(cls) -> 'SpanId':
        return cls(int=uuid4().int)


class MessageId(UUID):
    """Identity for a message within a span."""

    @classmethod
    def generate(cls) -> 'MessageId':
        return cls(int=uuid4().int)


class ContentBlockId(UUID):
    """Identity for an immutable text content block."""

    @classmethod
    def generate(cls) -> 'ContentBlockId':
        return cls(int=uuid4().int)


# Type aliases for entity subtypes - same UUID space, semantic distinction
ConversationId = EntityId
AssetId = EntityId
DocumentId = EntityId
TabId = UUID
RevisionId = UUID
UserId = UUID
MCPServerId = UUID
OAuthConnectionId = UUID
