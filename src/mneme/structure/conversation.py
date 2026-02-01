"""Conversation domain - Conversation/Turn/Span/Message structure.

Conversations are entities with a Turn→Span→Message hierarchy:
- Conversation: an entity that owns turn selections (replaces old "view"/"thread")
- Turn: a shared position where branching occurs (user turn or assistant turn)
- Span: one alternative at a turn (one model run's output)
- Message: a single message within a span

Multiple conversations can share turns and spans via selections.
Forks are tracked via EntityRelation with forked_from.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..ids import ConversationId, MessageId, SpanId, TurnId
from ..types import Role
from ..addressable.entity import Entity
from ..content.stored import StoredContent


@dataclass
class Conversation:
    """A conversation - an entity that owns a path through turns/spans."""

    entity: Entity
    system_prompt: Optional[str] = None

    @property
    def id(self) -> ConversationId:
        return self.entity.id


@dataclass
class Turn:
    """A shared position in a conversation where branching can occur."""

    id: TurnId
    role: Role
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Span:
    """One alternative at a turn - contains messages from one model run."""

    id: SpanId
    turn_id: TurnId
    model_id: Optional[str] = None
    message_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Message:
    """A single message within a span."""

    id: MessageId
    span_id: SpanId
    sequence: int
    role: Role
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MessageWithContent:
    """A message paired with its resolved content references."""

    message: Message
    content: list[StoredContent]


@dataclass
class TurnWithContent:
    """A turn with its selected span and messages - for conversation path queries."""

    turn: Turn
    span: Span
    messages: list[MessageWithContent]
