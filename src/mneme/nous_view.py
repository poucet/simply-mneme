"""MnemeConversationView — storage-backed nous ConversationView.

Implements the nous ConversationView protocol using mneme stores.
Handles get_messages() and add_message() via Turn/Span/Message storage
with nous↔mneme content conversion via the content bridge.

History is loaded once on first get_messages() call and cached in memory.
Subsequent add_message() calls append to the cache, so the DB is only
read once per view lifetime.

Streaming callbacks (on_text_delta, on_content_block, call_tool) are no-ops
here — consumers like Episteme subclass and override them to add WebSocket
streaming, tool execution, etc.

Requires the 'nous' optional dependency: pip install simply-mneme[nous]
"""

import logging
from typing import Optional

from nous.types import Message as NousMessage
from nous.types.content import (
    ContentBlock as NousContentBlock,
    TextContent as NousTextContent,
)
from nous.types.tool import ToolCall, ToolResult

from .content.nous_bridge import nous_to_stored, stored_to_nous
from .content.protocol import AssetStore, ContentStore
from .structure.conversation import Conversation
from .structure.protocol import ConversationStore
from .types import ContentOrigin, Role

logger = logging.getLogger(__name__)


class MnemeConversationView:
    """Storage-backed nous ConversationView.

    Reads and writes conversation history via mneme stores.
    History is cached after the first load — add_message() appends to cache.

    Subclass and override on_text_delta/on_content_block/call_tool/on_turn_complete
    to add streaming, tool execution, or other side effects.
    """

    def __init__(
        self,
        conversation: Conversation,
        conversation_store: ConversationStore,
        content_store: ContentStore,
        asset_store: AssetStore,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.conversation = conversation
        self.conversation_store = conversation_store
        self.content_store = content_store
        self.asset_store = asset_store
        self.provider = provider
        self.model = model

        # Cached message history (loaded once, grown by add_message)
        self._messages: Optional[list[NousMessage]] = None

        # Buffer for accumulating text during streaming
        self._text_buffer: list[str] = []

    # =========================================================================
    # Read: Engine pulls state
    # =========================================================================

    async def get_messages(self, limit: Optional[int] = None) -> list[NousMessage]:
        """Get conversation history as nous Messages.

        First call loads from storage and caches. Subsequent calls return
        the cached list (which grows as add_message is called).
        """
        if self._messages is None:
            self._messages = await self._load_messages()

        if limit is not None:
            return self._messages[-limit:]
        return list(self._messages)

    async def _load_messages(self) -> list[NousMessage]:
        """Load full conversation history from storage."""
        result: list[NousMessage] = []

        # Prepend system prompt if present
        if self.conversation.system_prompt:
            result.append(NousMessage(
                role="system",
                content=[NousTextContent(text=self.conversation.system_prompt)],
            ))

        # Get the conversation path (turns with selected spans and messages)
        path = await self.conversation_store.get_conversation_path(
            self.conversation.id
        )

        # Convert each message's StoredContent → nous ContentBlocks
        for turn_with_content in path:
            for msg_with_content in turn_with_content.messages:
                nous_blocks = await stored_to_nous(
                    msg_with_content.content,
                    self.content_store,
                    self.asset_store,
                )
                result.append(NousMessage(
                    id=str(msg_with_content.message.id),
                    role=msg_with_content.message.role.value,
                    content=nous_blocks,
                    provider=self.provider,
                    model=turn_with_content.span.model_id,
                ))

        return result

    # =========================================================================
    # Write: Engine pushes events
    # =========================================================================

    async def on_text_delta(self, text: str) -> None:
        """Called when streaming text arrives. Override for streaming."""
        self._text_buffer.append(text)

    async def on_content_block(self, block: NousContentBlock) -> None:
        """Called when a complete non-text content block is ready. Override for streaming."""
        pass

    async def call_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call. Override to provide tool execution."""
        return ToolResult(
            tool_use_id=tool_call.id,
            content=[NousTextContent(text="Tool calling is not configured")],
            is_error=True,
        )

    async def add_message(self, message: NousMessage) -> None:
        """Persist a message by creating a Turn + Span + Message in mneme.

        Each add_message() call creates a new Turn (shared across forks)
        with a Span (this model run's version) and stores the content.
        The message is also appended to the in-memory cache.
        """
        role = Role(message.role)
        model_id = message.model or self.model

        # Determine content origin from role
        origin = ContentOrigin.ASSISTANT if role == Role.ASSISTANT else ContentOrigin.USER

        # Create Turn → Span → select → store content → add Message
        turn = await self.conversation_store.create_turn(role)
        span = await self.conversation_store.create_span(turn.id, model_id=model_id)
        await self.conversation_store.select_span(
            self.conversation.id, turn.id, span.id,
        )

        stored_content = await nous_to_stored(
            message.content,
            self.content_store,
            self.asset_store,
            origin,
            model_id=model_id,
        )

        await self.conversation_store.add_message(span.id, role, stored_content)

        # Append to cache so subsequent get_messages() calls include this message
        if self._messages is None:
            self._messages = []
        self._messages.append(message)

        # Clear text buffer after persisting
        self._text_buffer.clear()

    async def on_turn_complete(self) -> None:
        """Called when the entire turn is complete. Override for side effects."""
        pass

    # =========================================================================
    # Helpers
    # =========================================================================

    def get_accumulated_text(self) -> str:
        """Get all accumulated text from on_text_delta calls."""
        return "".join(self._text_buffer)
