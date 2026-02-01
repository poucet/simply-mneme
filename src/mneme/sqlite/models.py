"""SQLAlchemy ORM models for the UCM schema.

Tables are organized into three layers:
  Addressable: entities, entity_relations
  Structure:   views, turns, spans, view_selections, messages,
               documents, tabs, revisions, users
  Content:     content_blocks, assets
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def new_uuid() -> str:
    return str(uuid.uuid4())


def now_epoch_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def epoch_ms_to_datetime(epoch_ms: Optional[int]) -> Optional[datetime]:
    if epoch_ms is None:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)


def datetime_to_epoch_ms(dt: Optional[datetime]) -> Optional[int]:
    if dt is None:
        return None
    return int(dt.timestamp() * 1000)


def parse_uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    if value is None:
        return None
    return uuid.UUID(value)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ===== Layer 1: Addressable =====

class EntityModel(Base):
    __tablename__ = "entities"

    id = Column(Text, primary_key=True, default=new_uuid)
    type = Column(Text, nullable=False)  # EntityType value
    user_id = Column(Text, nullable=True)
    name = Column(Text, nullable=True)
    slug = Column(Text, nullable=True, unique=True)
    is_private = Column(Boolean, nullable=False, default=False)
    is_archived = Column(Boolean, nullable=False, default=False)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)
    updated_at = Column(BigInteger, nullable=False, default=now_epoch_ms, onupdate=now_epoch_ms)

    # Relationships (back-populated by subtype tables)
    conversation = relationship("ConversationModel", back_populates="entity", uselist=False)
    document = relationship("DocumentModel", back_populates="entity", uselist=False)

    __table_args__ = (
        Index("ix_entities_user_type", "user_id", "type"),
        Index("ix_entities_slug", "slug"),
    )


class EntityRelationModel(Base):
    __tablename__ = "entity_relations"

    id = Column(Text, primary_key=True, default=new_uuid)
    from_entity_id = Column(Text, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    to_entity_id = Column(Text, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(Text, nullable=False)  # RelationType value
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)

    __table_args__ = (
        Index("ix_entity_relations_from", "from_entity_id", "relation_type"),
        Index("ix_entity_relations_to", "to_entity_id", "relation_type"),
    )


# ===== Layer 2: Structure – Conversations =====

class ConversationModel(Base):
    __tablename__ = "conversations"

    id = Column(Text, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    system_prompt = Column(Text, nullable=True)
    last_model = Column(Text, nullable=True)
    summary_text = Column(Text, nullable=True)

    entity = relationship("EntityModel", back_populates="conversation")


class TurnModel(Base):
    __tablename__ = "turns"

    id = Column(Text, primary_key=True, default=new_uuid)
    role = Column(Text, nullable=False)  # Role value
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)

    spans = relationship("SpanModel", back_populates="turn")


class SpanModel(Base):
    __tablename__ = "spans"

    id = Column(Text, primary_key=True, default=new_uuid)
    turn_id = Column(Text, ForeignKey("turns.id", ondelete="CASCADE"), nullable=False)
    model_id = Column(Text, nullable=True)
    message_count = Column(Integer, nullable=False, default=0)
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)

    turn = relationship("TurnModel", back_populates="spans")
    messages = relationship("MessageModel", back_populates="span", order_by="MessageModel.sequence")

    __table_args__ = (
        Index("ix_spans_turn", "turn_id"),
    )


class ConversationSelectionModel(Base):
    """Links a conversation to a specific span at a specific turn."""
    __tablename__ = "conversation_selections"

    id = Column(Text, primary_key=True, default=new_uuid)
    conversation_id = Column(Text, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    turn_id = Column(Text, ForeignKey("turns.id", ondelete="CASCADE"), nullable=False)
    span_id = Column(Text, ForeignKey("spans.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, nullable=False)  # Order in the conversation's path

    __table_args__ = (
        Index("ix_conversation_selections_conv", "conversation_id", "position"),
        Index("ix_conversation_selections_conv_turn", "conversation_id", "turn_id", unique=True),
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(Text, primary_key=True, default=new_uuid)
    span_id = Column(Text, ForeignKey("spans.id", ondelete="CASCADE"), nullable=False)
    sequence = Column(Integer, nullable=False)  # Order within span
    role = Column(Text, nullable=False)  # Role value
    content = Column(JSON, nullable=False, default=list)  # list[StoredContent] as JSON
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)

    span = relationship("SpanModel", back_populates="messages")

    __table_args__ = (
        Index("ix_messages_span_seq", "span_id", "sequence"),
    )


# ===== Layer 2: Structure – Documents =====

class DocumentModel(Base):
    __tablename__ = "documents"

    id = Column(Text, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    source = Column(Text, nullable=False)  # DocumentSource value
    source_id = Column(Text, nullable=True)

    entity = relationship("EntityModel", back_populates="document")
    tabs = relationship("TabModel", back_populates="document")

    __table_args__ = (
        Index("ix_documents_source", "source", "source_id"),
    )


class TabModel(Base):
    __tablename__ = "tabs"

    id = Column(Text, primary_key=True, default=new_uuid)
    document_id = Column(Text, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    parent_tab_id = Column(Text, ForeignKey("tabs.id", ondelete="SET NULL"), nullable=True)
    tab_index = Column(Integer, nullable=False, default=0)
    title = Column(Text, nullable=False, default="")
    icon = Column(Text, nullable=True)
    content_markdown = Column(Text, nullable=True)
    referenced_assets = Column(JSON, nullable=False, default=list)  # list[AssetId as str]
    source_tab_id = Column(Text, nullable=True)  # External source tab ID (e.g. Google Docs)
    current_revision_id = Column(Text, nullable=True)  # Set after revision created
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)
    updated_at = Column(BigInteger, nullable=False, default=now_epoch_ms, onupdate=now_epoch_ms)

    document = relationship("DocumentModel", back_populates="tabs")
    revisions = relationship("RevisionModel", back_populates="tab")

    __table_args__ = (
        Index("ix_tabs_document", "document_id"),
    )


class RevisionModel(Base):
    __tablename__ = "revisions"

    id = Column(Text, primary_key=True, default=new_uuid)
    tab_id = Column(Text, ForeignKey("tabs.id", ondelete="CASCADE"), nullable=False)
    revision_number = Column(Integer, nullable=False)
    parent_revision_id = Column(Text, ForeignKey("revisions.id", ondelete="SET NULL"), nullable=True)
    content_markdown = Column(Text, nullable=False, default="")
    content_hash = Column(Text, nullable=False, default="")
    referenced_assets = Column(JSON, nullable=False, default=list)
    created_by = Column(Text, nullable=False)  # UserId
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)

    tab = relationship("TabModel", back_populates="revisions")

    __table_args__ = (
        Index("ix_revisions_tab", "tab_id"),
    )


# ===== Layer 2: Structure – Users =====

class UserModel(Base):
    __tablename__ = "users"

    id = Column(Text, primary_key=True, default=new_uuid)
    email = Column(Text, nullable=False, unique=True)
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)
    updated_at = Column(BigInteger, nullable=False, default=now_epoch_ms, onupdate=now_epoch_ms)


# ===== Layer 2: Structure – MCP Servers =====

class MCPServerModel(Base):
    __tablename__ = "mcp_servers"

    id = Column(Text, primary_key=True, default=new_uuid)
    name = Column(Text, nullable=False, unique=True)
    url = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    headers = Column(JSON, nullable=True)
    approval_mode = Column(Text, nullable=False, default="manual")
    auto_approve_tools = Column(JSON, nullable=False, default=list)
    settings = Column(JSON, nullable=False, default=dict)
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)
    updated_at = Column(BigInteger, nullable=False, default=now_epoch_ms, onupdate=now_epoch_ms)

    __table_args__ = (
        Index("ix_mcp_servers_name", "name", unique=True),
    )


# ===== Layer 3: Content =====

class ContentBlockModel(Base):
    __tablename__ = "content_blocks"

    id = Column(Text, primary_key=True, default=new_uuid)
    text = Column(Text, nullable=False)
    origin = Column(Text, nullable=False)  # ContentOrigin value
    model_id = Column(Text, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)


class AssetModel(Base):
    __tablename__ = "assets"

    id = Column(Text, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    mime_type = Column(Text, nullable=False)
    content_hash = Column(Text, nullable=False)  # SHA-256
    file_size = Column(BigInteger, nullable=False, default=0)
    original_filename = Column(Text, nullable=True)
    storage_path = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)

    __table_args__ = (
        Index("ix_assets_hash", "content_hash"),
    )
