"""MnemeConversationView — storage-backed nous ConversationView.

Implements the nous ConversationView protocol using mneme stores.
Handles get_messages() and add_message() via Turn/Span/Message storage
with nous↔mneme content conversion via the content bridge.

History is loaded once on first get_messages() call and cached in memory.
Messages added via add_message() are buffered in memory and only persisted
when on_turn_complete() is called — this is the "commit point" for storage.

Streaming callbacks (on_text_delta, on_content_block) are no-ops here —
consumers like Episteme compose and override them to add WebSocket streaming.
call_tool executes via nous ToolExecutor (if provided) and stores media assets.

Requires the 'nous' optional dependency: pip install simply-mneme[nous]
"""

import base64
import logging
from typing import Optional

from nous.types import Message as NousMessage
from nous.types.content import (
    AudioContent as NousAudioContent,
    ContentBlock as NousContentBlock,
    ImageContent as NousImageContent,
    TextContent as NousTextContent,
)
from nous.types.tool import ToolCall, ToolResult
from nous.mcp import ToolExecutor

from .content.media import store_media_from_result
from .content.nous_bridge import nous_to_stored, stored_to_nous
from .content.protocol import AssetStore, ContentStore
from .ids import AssetId, EntityId
from .structure.conversation import Conversation
from .structure.protocol import ConversationStore
from .types import ContentOrigin, Role


logger = logging.getLogger(__name__)


class MnemeConversationView:
    """Storage-backed nous ConversationView.

    Reads and writes conversation history via mneme stores.
    History is cached after the first load — add_message() appends to cache.

    Messages are buffered in memory until on_turn_complete() is called,
    which persists all pending messages to storage (the "commit point").

    Tool execution is handled via an optional nous ToolExecutor. Media assets
    from tool results are automatically stored. Override on_text_delta,
    on_content_block for streaming and side effects.
    """

    def __init__(
        self,
        conversation: Conversation,
        conversation_store: ConversationStore,
        content_store: ContentStore,
        asset_store: AssetStore,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        tool_executor: Optional[ToolExecutor] = None,
    ):
        self.conversation = conversation
        self.conversation_store = conversation_store
        self.content_store = content_store
        self.asset_store = asset_store
        self.provider = provider
        self.model = model
        self._tool_executor = tool_executor

        # Cached message history (loaded once, grown by add_message)
        self._messages: Optional[list[NousMessage]] = None

        # Messages buffered since last commit (persisted in on_turn_complete)
        self._pending_messages: list[NousMessage] = []

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
        """Store media assets for later retrieval on conversation reload."""
        if isinstance(block, (NousImageContent, NousAudioContent)) and block.data:
            await self.asset_store.store_asset(
                entity_id=EntityId.generate(),
                data=base64.b64decode(block.data),
                mime_type=block.mime_type,
            )

    async def call_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call via nous ToolExecutor and store media assets."""
        if not self._tool_executor:
            return ToolResult(
                tool_call_id=tool_call.id,
                content=[NousTextContent(text="Tool calling is not configured")],
                is_error=True,
            )

        result = await self._tool_executor.execute(tool_call)
        await store_media_from_result(result, tool_call.name, self.asset_store)
        return result

    async def add_message(self, message: NousMessage) -> None:
        """Buffer a message for later persistence.

        Resolves any unresolved asset references (asset_id without data)
        before buffering, so the engine always sees complete content.
        Defers storage writes to on_turn_complete().
        """
        content = await self._resolve_assets(message.content)
        if content is not message.content:
            message = NousMessage(
                id=message.id, role=message.role, content=content,
                provider=message.provider, model=message.model,
            )

        if self._messages is None:
            self._messages = []
        self._messages.append(message)
        self._pending_messages.append(message)

        # Clear text buffer after each message
        self._text_buffer.clear()

    async def on_turn_complete(self) -> None:
        """Persist all pending messages to storage (the commit point).

        Creates Turn → Span → Message for each buffered message, then
        clears the pending buffer.
        """
        for message in self._pending_messages:
            await self._persist_message(message)
        self._pending_messages.clear()

    async def _persist_message(self, message: NousMessage) -> None:
        """Persist a single message as a Turn + Span + Message in mneme."""
        role = Role(message.role)
        model_id = message.model or self.model

        origin = ContentOrigin.ASSISTANT if role == Role.ASSISTANT else ContentOrigin.USER

        turn = await self.conversation_store.create_turn(role)
        span = await self.conversation_store.create_span(turn.id, model_id=model_id)

        stored_content = await nous_to_stored(
            message.content,
            self.content_store,
            self.asset_store,
            origin,
            model_id=model_id,
        )

        await self.conversation_store.add_message(span.id, role, stored_content)

        await self.conversation_store.select_span(
            self.conversation.id, turn.id, span.id,
        )

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _resolve_assets(
        self, blocks: list[NousContentBlock],
    ) -> list[NousContentBlock]:
        """Resolve unresolved asset references to base64 data.

        Blocks with asset_id but no data are resolved from the asset
        store. Returns the original list unchanged if nothing needed resolution.
        """
        result: list[NousContentBlock] | None = None

        for i, block in enumerate(blocks):
            if isinstance(block, (NousImageContent, NousAudioContent)):
                if block.asset_id and not block.data:
                    if result is None:
                        result = list(blocks[:i])
                    data = await self.asset_store.get_asset_data(
                        AssetId(block.asset_id),
                    )
                    if data:
                        b64 = base64.b64encode(data).decode("ascii")
                        result.append(block.model_copy(update={"data": b64}))
                    continue
            if result is not None:
                result.append(block)

        return result if result is not None else blocks

    def get_accumulated_text(self) -> str:
        """Get all accumulated text from on_text_delta calls."""
        return "".join(self._text_buffer)
