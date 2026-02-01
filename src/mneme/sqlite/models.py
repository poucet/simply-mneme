"""SQLAlchemy ORM models aligned with the noema database schema.

Tables are organized into three layers:
  Addressable: entities, entity_relations
  Structure:   conversations, turns, spans, conversation_selections, messages,
               message_content, documents, document_tabs, document_revisions, users
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
    PrimaryKeyConstraint,
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
    entity_type = Column(Text, nullable=False)  # EntityType value
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    name = Column(Text, nullable=True)
    slug = Column(Text, nullable=True, unique=True)
    is_private = Column(Boolean, nullable=False, default=True)
    is_archived = Column(Boolean, nullable=False, default=False)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)
    updated_at = Column(BigInteger, nullable=False, default=now_epoch_ms, onupdate=now_epoch_ms)

    # Relationships (back-populated by subtype tables)
    conversation = relationship("ConversationModel", back_populates="entity", uselist=False)
    document = relationship("DocumentModel", back_populates="entity", uselist=False)

    __table_args__ = (
        Index("idx_entities_user", "user_id"),
        Index("idx_entities_type", "entity_type"),
        Index("idx_entities_slug", "slug"),
        Index("idx_entities_created", "created_at"),
        Index("idx_entities_updated", "updated_at"),
        Index("idx_entities_user_updated", "user_id", "updated_at"),
    )


class EntityRelationModel(Base):
    __tablename__ = "entity_relations"

    from_id = Column(Text, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    to_id = Column(Text, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    relation = Column(Text, nullable=False)  # RelationType value
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)

    __table_args__ = (
        PrimaryKeyConstraint("from_id", "to_id", "relation"),
        Index("idx_entity_relations_to", "to_id", "relation"),
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
    # message_count is computed dynamically, not stored as a column
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)

    turn = relationship("TurnModel", back_populates="spans")
    messages = relationship(
        "MessageModel", back_populates="span",
        order_by="MessageModel.sequence_number",
    )

    __table_args__ = (
        Index("idx_spans_turn", "turn_id"),
    )


class ConversationSelectionModel(Base):
    """Links a conversation to a specific span at a specific turn."""
    __tablename__ = "conversation_selections"

    # Composite PK: (conversation_id, turn_id)
    conversation_id = Column(Text, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    turn_id = Column(Text, ForeignKey("turns.id", ondelete="CASCADE"), nullable=False)
    span_id = Column(Text, ForeignKey("spans.id", ondelete="CASCADE"), nullable=False)
    sequence_number = Column(Integer, nullable=False)  # Order in the conversation's path

    __table_args__ = (
        PrimaryKeyConstraint("conversation_id", "turn_id"),
        Index("idx_conversation_selections_conv_seq", "conversation_id", "sequence_number"),
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(Text, primary_key=True, default=new_uuid)
    span_id = Column(Text, ForeignKey("spans.id", ondelete="CASCADE"), nullable=False)
    sequence_number = Column(Integer, nullable=False)  # Order within span
    role = Column(Text, nullable=False)  # Role value
    # Content is stored in the message_content table, not inline
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)

    span = relationship("SpanModel", back_populates="messages")
    content_items = relationship(
        "MessageContentModel", back_populates="message",
        order_by="MessageContentModel.sequence_number",
    )

    __table_args__ = (
        Index("idx_messages_span", "span_id", "sequence_number"),
    )


class MessageContentModel(Base):
    """Individual content item within a message (text, asset, tool call, etc.)."""
    __tablename__ = "message_content"

    id = Column(Text, primary_key=True, default=new_uuid)
    message_id = Column(Text, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    sequence_number = Column(Integer, nullable=False)
    content_type = Column(Text, nullable=False)  # 'text', 'asset_ref', 'document_ref', 'tool_call', 'tool_result'
    content_block_id = Column(Text, ForeignKey("content_blocks.id"), nullable=True)
    asset_id = Column(Text, nullable=True)
    mime_type = Column(Text, nullable=True)
    document_id = Column(Text, nullable=True)
    tool_data = Column(Text, nullable=True)  # JSON string for tool_call/tool_result

    message = relationship("MessageModel", back_populates="content_items")

    __table_args__ = (
        Index("idx_message_content_message", "message_id", "sequence_number"),
        Index("idx_message_content_block", "content_block_id"),
    )


# ===== Layer 2: Structure – Documents =====

class DocumentModel(Base):
    __tablename__ = "documents"

    id = Column(Text, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    title = Column(Text, nullable=False, default="")
    source = Column(Text, nullable=False)  # DocumentSource value
    source_id = Column(Text, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)
    updated_at = Column(BigInteger, nullable=False, default=now_epoch_ms, onupdate=now_epoch_ms)

    entity = relationship("EntityModel", back_populates="document")
    tabs = relationship("TabModel", back_populates="document")

    __table_args__ = (
        Index("idx_documents_source", "source", "source_id"),
    )


class TabModel(Base):
    __tablename__ = "document_tabs"

    id = Column(Text, primary_key=True, default=new_uuid)
    document_id = Column(Text, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    parent_tab_id = Column(Text, ForeignKey("document_tabs.id", ondelete="SET NULL"), nullable=True)
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
        Index("idx_document_tabs_document", "document_id"),
    )


class RevisionModel(Base):
    __tablename__ = "document_revisions"

    id = Column(Text, primary_key=True, default=new_uuid)
    tab_id = Column(Text, ForeignKey("document_tabs.id", ondelete="CASCADE"), nullable=False)
    revision_number = Column(Integer, nullable=False)
    parent_revision_id = Column(Text, ForeignKey("document_revisions.id", ondelete="SET NULL"), nullable=True)
    content_markdown = Column(Text, nullable=False, default="")
    content_hash = Column(Text, nullable=False, default="")
    referenced_assets = Column(JSON, nullable=False, default=list)
    created_by = Column(Text, nullable=False)  # UserId
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)

    tab = relationship("TabModel", back_populates="revisions")

    __table_args__ = (
        Index("idx_document_revisions_tab", "tab_id"),
    )


# ===== Layer 2: Structure – Users =====

class UserModel(Base):
    __tablename__ = "users"

    id = Column(Text, primary_key=True, default=new_uuid)
    email = Column(Text, nullable=False, unique=True)
    # Encrypted API keys — managed by noema, not mneme
    encrypted_anthropic_key = Column(Text, nullable=True)
    encrypted_openai_key = Column(Text, nullable=True)
    encrypted_gemini_key = Column(Text, nullable=True)
    google_oauth_refresh_token = Column(Text, nullable=True)
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
        Index("idx_mcp_servers_name", "name", unique=True),
    )


# ===== Layer 2: Structure – OAuth Connections =====

class OAuthConnectionModel(Base):
    __tablename__ = "oauth_connections"

    id = Column(Text, primary_key=True, default=new_uuid)
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(Text, nullable=False)
    provider_user_id = Column(Text, nullable=True)
    provider_email = Column(Text, nullable=True)
    scopes = Column(JSON, nullable=False, default=list)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(BigInteger, nullable=True)  # Epoch ms
    connection_name = Column(Text, nullable=True)
    provider_metadata = Column(JSON, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)
    updated_at = Column(BigInteger, nullable=False, default=now_epoch_ms)
    last_used_at = Column(BigInteger, nullable=True)  # Epoch ms

    __table_args__ = (
        Index("idx_oauth_connections_user_provider", "user_id", "provider"),
        Index("idx_oauth_connections_user_provider_active", "user_id", "provider", "is_active"),
    )


# ===== Layer 3: Content =====

class ContentBlockModel(Base):
    __tablename__ = "content_blocks"

    id = Column(Text, primary_key=True, default=new_uuid)
    content_hash = Column(Text, nullable=False)
    content_type = Column(Text, nullable=False, default="plain")
    text = Column(Text, nullable=False)
    is_private = Column(Boolean, nullable=False, default=False)
    origin_kind = Column(Text, nullable=False)  # ContentOrigin value
    origin_user_id = Column(Text, nullable=True)
    origin_model_id = Column(Text, nullable=True)
    origin_source_id = Column(Text, nullable=True)
    origin_parent_id = Column(Text, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)


class AssetModel(Base):
    __tablename__ = "assets"

    id = Column(Text, primary_key=True)
    blob_hash = Column(Text, nullable=False)  # SHA-256
    mime_type = Column(Text, nullable=False)
    size_bytes = Column(BigInteger, nullable=False, default=0)
    is_private = Column(Boolean, nullable=False, default=False)
    created_at = Column(BigInteger, nullable=False, default=now_epoch_ms)

    __table_args__ = (
        Index("idx_assets_hash", "blob_hash"),
    )
