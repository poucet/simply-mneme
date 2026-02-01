"""Structure layer abstract stores - ConversationStore, DocumentStore, UserStore, MCPServerStore."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from ..ids import (
    AssetId,
    ConversationId,
    DocumentId,
    MCPServerId,
    MessageId,
    RevisionId,
    SpanId,
    TabId,
    TurnId,
    UserId,
)
from ..types import DocumentSource, Role
from ..content.stored import StoredContent
from .conversation import Conversation, Message, Span, Turn, TurnWithContent
from .document import Document, Revision, Tab
from .mcp_server import MCPServer
from .user import User


class ConversationStore(ABC):
    """Abstract store for conversation structure."""

    # -- Conversation management --

    @abstractmethod
    async def create_conversation(
        self,
        user_id: UserId,
        title: str,
        system_prompt: Optional[str] = None,
    ) -> Conversation: ...

    @abstractmethod
    async def get_conversation(self, conversation_id: ConversationId) -> Optional[Conversation]: ...

    @abstractmethod
    async def list_conversations(
        self,
        user_id: UserId,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[Conversation]: ...

    @abstractmethod
    async def update_conversation(
        self,
        conversation_id: ConversationId,
        system_prompt: Optional[str] = None,
        last_model: Optional[str] = None,
        summary_text: Optional[str] = None,
    ) -> Conversation: ...

    @abstractmethod
    async def delete_conversation(self, conversation_id: ConversationId) -> bool: ...

    # -- Turn / Span / Message --

    @abstractmethod
    async def create_turn(self, role: Role) -> Turn: ...

    @abstractmethod
    async def get_turn(self, turn_id: TurnId) -> Optional[Turn]: ...

    @abstractmethod
    async def create_span(
        self,
        turn_id: TurnId,
        model_id: Optional[str] = None,
    ) -> Span: ...

    @abstractmethod
    async def get_spans(self, turn_id: TurnId) -> list[Span]: ...

    @abstractmethod
    async def add_message(
        self,
        span_id: SpanId,
        role: Role,
        content: list[StoredContent],
    ) -> Message: ...

    @abstractmethod
    async def get_messages(self, span_id: SpanId) -> list[Message]: ...

    # -- Selection management --

    @abstractmethod
    async def select_span(
        self,
        conversation_id: ConversationId,
        turn_id: TurnId,
        span_id: SpanId,
    ) -> None: ...

    @abstractmethod
    async def get_selected_span(
        self,
        conversation_id: ConversationId,
        turn_id: TurnId,
    ) -> Optional[SpanId]: ...

    # -- Path queries --

    @abstractmethod
    async def get_conversation_path(self, conversation_id: ConversationId) -> list[TurnWithContent]: ...

    @abstractmethod
    async def get_context_at(
        self,
        conversation_id: ConversationId,
        up_to_turn_id: TurnId,
    ) -> list[TurnWithContent]: ...

    # -- Branching --

    @abstractmethod
    async def fork_conversation(
        self,
        conversation_id: ConversationId,
        at_turn_id: TurnId,
    ) -> Conversation: ...

    @abstractmethod
    async def copy_selections(
        self,
        from_conversation_id: ConversationId,
        to_conversation_id: ConversationId,
        up_to_turn_id: TurnId,
        include_turn: bool = False,
    ) -> int: ...

    @abstractmethod
    async def get_turn_count(self, conversation_id: ConversationId) -> int: ...


class DocumentStore(ABC):
    """Abstract store for document structure."""

    # -- Document CRUD --

    @abstractmethod
    async def create_document(
        self,
        user_id: UserId,
        title: str,
        source: DocumentSource,
        source_id: Optional[str] = None,
    ) -> Document: ...

    @abstractmethod
    async def get_document(self, document_id: DocumentId) -> Optional[Document]: ...

    @abstractmethod
    async def get_document_by_source(
        self,
        user_id: UserId,
        source: DocumentSource,
        source_id: str,
    ) -> Optional[Document]: ...

    @abstractmethod
    async def list_documents(
        self,
        user_id: UserId,
        source: Optional[DocumentSource] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Document]: ...

    @abstractmethod
    async def search_documents(
        self,
        user_id: UserId,
        query: str,
        limit: int = 20,
    ) -> list[Document]: ...

    @abstractmethod
    async def update_document_title(
        self,
        document_id: DocumentId,
        title: str,
    ) -> None: ...

    @abstractmethod
    async def delete_document(self, document_id: DocumentId) -> bool: ...

    # -- Tab CRUD --

    @abstractmethod
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
    ) -> Tab: ...

    @abstractmethod
    async def get_tab(self, tab_id: TabId) -> Optional[Tab]: ...

    @abstractmethod
    async def list_tabs(self, document_id: DocumentId) -> list[Tab]: ...

    @abstractmethod
    async def get_tab_by_source_id(
        self,
        document_id: DocumentId,
        source_tab_id: str,
    ) -> Optional[Tab]: ...

    @abstractmethod
    async def get_child_tabs(self, parent_tab_id: TabId) -> list[Tab]: ...

    @abstractmethod
    async def update_tab(
        self,
        tab_id: TabId,
        title: Optional[str] = None,
        icon: Optional[str] = None,
        content_markdown: Optional[str] = None,
        referenced_assets: Optional[list[AssetId]] = None,
        tab_index: Optional[int] = None,
        parent_tab_id: Optional[TabId] = None,
    ) -> Tab: ...

    @abstractmethod
    async def delete_tabs(self, document_id: DocumentId) -> int:
        """Delete all tabs for a document. Returns count of deleted tabs."""
        ...

    @abstractmethod
    async def set_tab_revision(
        self,
        tab_id: TabId,
        revision_id: RevisionId,
    ) -> None: ...

    @abstractmethod
    async def delete_tab(self, tab_id: TabId) -> bool: ...

    # -- Revision CRUD --

    @abstractmethod
    async def create_revision(
        self,
        tab_id: TabId,
        content_markdown: str,
        content_hash: str,
        created_by: UserId,
        referenced_assets: Optional[list[AssetId]] = None,
    ) -> Revision: ...

    @abstractmethod
    async def get_revision(self, revision_id: RevisionId) -> Optional[Revision]: ...

    @abstractmethod
    async def list_revisions(self, tab_id: TabId) -> list[Revision]: ...

    @abstractmethod
    async def promote_from_message(
        self,
        message_id: MessageId,
        user_id: UserId,
        title: Optional[str] = None,
    ) -> Document: ...


class UserStore(ABC):
    """Abstract store for user management."""

    @abstractmethod
    async def get_user(self, user_id: UserId) -> Optional[User]: ...

    @abstractmethod
    async def get_user_by_email(self, email: str) -> Optional[User]: ...

    @abstractmethod
    async def create_user(self, email: str) -> User: ...

    @abstractmethod
    async def get_or_create_user(self, email: str) -> User:
        """Get user by email or create if not found."""
        ...

    @abstractmethod
    async def update_user(
        self,
        user_id: UserId,
        email: Optional[str] = None,
    ) -> User: ...


class MCPServerStore(ABC):
    """Abstract store for MCP server configurations.

    Manages server registrations with a unified approval model:
        approval_mode: Server-level default ("manual" or "auto")
        auto_approve_tools: Tool-level exceptions that skip approval
    """

    @abstractmethod
    async def get_server(self, server_id: MCPServerId) -> Optional[MCPServer]: ...

    @abstractmethod
    async def get_server_by_name(self, name: str) -> Optional[MCPServer]: ...

    @abstractmethod
    async def list_servers(self, enabled_only: bool = False) -> list[MCPServer]: ...

    @abstractmethod
    async def create_server(
        self,
        name: str,
        url: str,
        enabled: bool = True,
        headers: Optional[dict[str, str]] = None,
        approval_mode: str = "manual",
        auto_approve_tools: Optional[list[str]] = None,
        settings: Optional[dict[str, Any]] = None,
    ) -> MCPServer: ...

    @abstractmethod
    async def update_server(
        self,
        server_id: MCPServerId,
        name: Optional[str] = None,
        url: Optional[str] = None,
        enabled: Optional[bool] = None,
        headers: Optional[dict[str, str]] = None,
        approval_mode: Optional[str] = None,
        auto_approve_tools: Optional[list[str]] = None,
        settings: Optional[dict[str, Any]] = None,
    ) -> MCPServer: ...

    @abstractmethod
    async def delete_server(self, server_id: MCPServerId) -> bool: ...
