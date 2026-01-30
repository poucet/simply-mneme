"""Tests for mneme.content.nous_bridge — nous ↔ mneme content conversion."""

import base64
from typing import Optional
from uuid import uuid4

import pytest

from mneme.content.nous_bridge import nous_to_stored, stored_to_nous
from mneme.content.protocol import AssetStore, ContentStore
from mneme.content.stored import (
    AssetRef,
    DocumentRef,
    StoredContent,
    TextRef,
    ToolCall,
    ToolResult,
)
from mneme.ids import AssetId, ContentBlockId, EntityId
from mneme.types import ContentOrigin

from nous.types.content import (
    AudioContent as NousAudioContent,
    ImageContent as NousImageContent,
    TextContent as NousTextContent,
    ToolResultContent as NousToolResultContent,
    ToolUseContent as NousToolUseContent,
)


# ---------------------------------------------------------------------------
# In-memory store fakes
# ---------------------------------------------------------------------------

class FakeContentStore(ContentStore):
    """In-memory ContentStore for testing."""

    def __init__(self) -> None:
        self._texts: dict[ContentBlockId, str] = {}

    async def store_text(
        self,
        text: str,
        origin: ContentOrigin,
        model_id: Optional[str] = None,
    ) -> ContentBlockId:
        cid = ContentBlockId.generate()
        self._texts[cid] = text
        return cid

    async def get_text(self, content_block_id: ContentBlockId) -> Optional[str]:
        return self._texts.get(content_block_id)

    async def get_content_block(self, content_block_id: ContentBlockId):
        return None

    async def resolve_content(self, refs: list[StoredContent]):
        return []


class FakeAssetStore(AssetStore):
    """In-memory AssetStore for testing."""

    def __init__(self) -> None:
        self._assets: dict[AssetId, tuple[bytes, str]] = {}

    async def store_asset(
        self,
        entity_id: EntityId,
        data: bytes,
        mime_type: str,
        original_filename: Optional[str] = None,
    ) -> AssetId:
        aid = AssetId.generate()
        self._assets[aid] = (data, mime_type)
        return aid

    async def get_asset_data(self, asset_id: AssetId) -> Optional[bytes]:
        entry = self._assets.get(asset_id)
        return entry[0] if entry else None

    async def get_asset_metadata(self, asset_id: AssetId) -> Optional[dict]:
        return None

    async def delete_asset(self, asset_id: AssetId) -> bool:
        return self._assets.pop(asset_id, None) is not None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def content_store() -> FakeContentStore:
    return FakeContentStore()


@pytest.fixture
def asset_store() -> FakeAssetStore:
    return FakeAssetStore()


# ---------------------------------------------------------------------------
# stored_to_nous: resolving mneme refs into nous inline content
# ---------------------------------------------------------------------------

class TestStoredToNous:
    """Tests for stored_to_nous (mneme → nous direction)."""

    async def test_text_ref_resolves_to_text_content(self, content_store, asset_store):
        cid = await content_store.store_text("hello world", ContentOrigin.USER)
        refs: list[StoredContent] = [TextRef(content_block_id=cid)]

        blocks = await stored_to_nous(refs, content_store, asset_store)

        assert len(blocks) == 1
        assert isinstance(blocks[0], NousTextContent)
        assert blocks[0].text == "hello world"

    async def test_text_ref_missing_returns_empty(self, content_store, asset_store):
        bogus_cid = ContentBlockId.generate()
        refs: list[StoredContent] = [TextRef(content_block_id=bogus_cid)]

        blocks = await stored_to_nous(refs, content_store, asset_store)

        assert blocks == []

    async def test_image_asset_ref_resolves_to_image_content(self, content_store, asset_store):
        raw = b"\x89PNG\r\n\x1a\nfake-png-data"
        aid = await asset_store.store_asset(EntityId.generate(), raw, "image/png")
        refs: list[StoredContent] = [AssetRef(asset_id=aid, mime_type="image/png")]

        blocks = await stored_to_nous(refs, content_store, asset_store)

        assert len(blocks) == 1
        assert isinstance(blocks[0], NousImageContent)
        assert blocks[0].mime_type == "image/png"
        assert base64.b64decode(blocks[0].data) == raw
        assert blocks[0].attachment_id == str(aid)

    async def test_audio_asset_ref_resolves_to_audio_content(self, content_store, asset_store):
        raw = b"RIFF....WAVEfmt fake-audio"
        aid = await asset_store.store_asset(EntityId.generate(), raw, "audio/wav")
        refs: list[StoredContent] = [AssetRef(asset_id=aid, mime_type="audio/wav")]

        blocks = await stored_to_nous(refs, content_store, asset_store)

        assert len(blocks) == 1
        assert isinstance(blocks[0], NousAudioContent)
        assert blocks[0].mime_type == "audio/wav"
        assert base64.b64decode(blocks[0].data) == raw

    async def test_missing_asset_returns_empty(self, content_store, asset_store):
        bogus_aid = AssetId.generate()
        refs: list[StoredContent] = [AssetRef(asset_id=bogus_aid, mime_type="image/png")]

        blocks = await stored_to_nous(refs, content_store, asset_store)

        assert blocks == []

    async def test_document_ref_skipped(self, content_store, asset_store):
        from mneme.ids import DocumentId
        refs: list[StoredContent] = [DocumentRef(document_id=DocumentId.generate())]

        blocks = await stored_to_nous(refs, content_store, asset_store)

        assert blocks == []

    async def test_tool_call_resolves_to_tool_use(self, content_store, asset_store):
        refs: list[StoredContent] = [
            ToolCall(id="call_123", name="search", input={"query": "test"})
        ]

        blocks = await stored_to_nous(refs, content_store, asset_store)

        assert len(blocks) == 1
        assert isinstance(blocks[0], NousToolUseContent)
        assert blocks[0].id == "call_123"
        assert blocks[0].name == "search"
        assert blocks[0].input == {"query": "test"}

    async def test_tool_result_with_text_content(self, content_store, asset_store):
        cid = await content_store.store_text("result text", ContentOrigin.ASSISTANT)
        refs: list[StoredContent] = [
            ToolResult(
                tool_use_id="call_123",
                content=(TextRef(content_block_id=cid),),
                is_error=False,
            )
        ]

        blocks = await stored_to_nous(refs, content_store, asset_store)

        assert len(blocks) == 1
        result = blocks[0]
        assert isinstance(result, NousToolResultContent)
        assert result.tool_use_id == "call_123"
        assert result.is_error is False
        assert len(result.content) == 1
        assert isinstance(result.content[0], NousTextContent)
        assert result.content[0].text == "result text"

    async def test_tool_result_with_error(self, content_store, asset_store):
        cid = await content_store.store_text("error msg", ContentOrigin.SYSTEM)
        refs: list[StoredContent] = [
            ToolResult(
                tool_use_id="call_456",
                content=(TextRef(content_block_id=cid),),
                is_error=True,
            )
        ]

        blocks = await stored_to_nous(refs, content_store, asset_store)

        assert len(blocks) == 1
        result = blocks[0]
        assert isinstance(result, NousToolResultContent)
        assert result.is_error is True

    async def test_tool_result_with_image_content(self, content_store, asset_store):
        raw = b"screenshot-bytes"
        aid = await asset_store.store_asset(EntityId.generate(), raw, "image/png")
        refs: list[StoredContent] = [
            ToolResult(
                tool_use_id="call_789",
                content=(AssetRef(asset_id=aid, mime_type="image/png"),),
            )
        ]

        blocks = await stored_to_nous(refs, content_store, asset_store)

        assert len(blocks) == 1
        result = blocks[0]
        assert isinstance(result, NousToolResultContent)
        assert len(result.content) == 1
        assert isinstance(result.content[0], NousImageContent)

    async def test_tool_result_empty_content(self, content_store, asset_store):
        refs: list[StoredContent] = [
            ToolResult(tool_use_id="call_empty", content=(), is_error=False)
        ]

        blocks = await stored_to_nous(refs, content_store, asset_store)

        assert len(blocks) == 1
        result = blocks[0]
        assert isinstance(result, NousToolResultContent)
        assert result.content == []

    async def test_multiple_refs_mixed(self, content_store, asset_store):
        cid = await content_store.store_text("some text", ContentOrigin.ASSISTANT)
        raw = b"image-data"
        aid = await asset_store.store_asset(EntityId.generate(), raw, "image/jpeg")

        refs: list[StoredContent] = [
            TextRef(content_block_id=cid),
            AssetRef(asset_id=aid, mime_type="image/jpeg"),
            ToolCall(id="c1", name="tool", input={}),
        ]

        blocks = await stored_to_nous(refs, content_store, asset_store)

        assert len(blocks) == 3
        assert isinstance(blocks[0], NousTextContent)
        assert isinstance(blocks[1], NousImageContent)
        assert isinstance(blocks[2], NousToolUseContent)

    async def test_empty_refs_returns_empty(self, content_store, asset_store):
        blocks = await stored_to_nous([], content_store, asset_store)
        assert blocks == []


# ---------------------------------------------------------------------------
# nous_to_stored: storing nous inline content as mneme refs
# ---------------------------------------------------------------------------

class TestNousToStored:
    """Tests for nous_to_stored (nous → mneme direction)."""

    async def test_text_content_stored_as_text_ref(self, content_store, asset_store):
        blocks = [NousTextContent(text="hello")]

        refs = await nous_to_stored(
            blocks, content_store, asset_store, ContentOrigin.USER
        )

        assert len(refs) == 1
        assert isinstance(refs[0], TextRef)
        # Verify it was actually stored
        text = await content_store.get_text(refs[0].content_block_id)
        assert text == "hello"

    async def test_text_content_with_model_id(self, content_store, asset_store):
        blocks = [NousTextContent(text="response")]

        refs = await nous_to_stored(
            blocks, content_store, asset_store,
            ContentOrigin.ASSISTANT, model_id="anthropic:claude-3-5-sonnet",
        )

        assert len(refs) == 1
        assert isinstance(refs[0], TextRef)

    async def test_image_content_stored_as_asset_ref(self, content_store, asset_store):
        raw = b"fake-image-bytes"
        b64 = base64.b64encode(raw).decode()
        blocks = [NousImageContent(mime_type="image/png", data=b64)]

        refs = await nous_to_stored(
            blocks, content_store, asset_store, ContentOrigin.ASSISTANT
        )

        assert len(refs) == 1
        assert isinstance(refs[0], AssetRef)
        assert refs[0].mime_type == "image/png"
        # Verify the binary was stored
        stored_data = await asset_store.get_asset_data(refs[0].asset_id)
        assert stored_data == raw

    async def test_image_without_data_returns_empty(self, content_store, asset_store):
        blocks = [NousImageContent(mime_type="image/png", data=None)]

        refs = await nous_to_stored(
            blocks, content_store, asset_store, ContentOrigin.ASSISTANT
        )

        assert refs == []

    async def test_audio_content_stored_as_asset_ref(self, content_store, asset_store):
        raw = b"fake-audio-bytes"
        b64 = base64.b64encode(raw).decode()
        blocks = [NousAudioContent(mime_type="audio/mp3", data=b64)]

        refs = await nous_to_stored(
            blocks, content_store, asset_store, ContentOrigin.ASSISTANT
        )

        assert len(refs) == 1
        assert isinstance(refs[0], AssetRef)
        assert refs[0].mime_type == "audio/mp3"
        stored_data = await asset_store.get_asset_data(refs[0].asset_id)
        assert stored_data == raw

    async def test_audio_without_data_returns_empty(self, content_store, asset_store):
        blocks = [NousAudioContent(mime_type="audio/wav", data=None)]

        refs = await nous_to_stored(
            blocks, content_store, asset_store, ContentOrigin.ASSISTANT
        )

        assert refs == []

    async def test_tool_use_stored_as_tool_call(self, content_store, asset_store):
        blocks = [
            NousToolUseContent(
                id="toolu_abc", name="web_search", input={"query": "weather"}
            )
        ]

        refs = await nous_to_stored(
            blocks, content_store, asset_store, ContentOrigin.ASSISTANT
        )

        assert len(refs) == 1
        assert isinstance(refs[0], ToolCall)
        assert refs[0].id == "toolu_abc"
        assert refs[0].name == "web_search"
        assert refs[0].input == {"query": "weather"}

    async def test_tool_result_with_text(self, content_store, asset_store):
        blocks = [
            NousToolResultContent(
                tool_use_id="toolu_abc",
                content=[NousTextContent(text="sunny, 72°F")],
                is_error=False,
            )
        ]

        refs = await nous_to_stored(
            blocks, content_store, asset_store, ContentOrigin.SYSTEM
        )

        assert len(refs) == 1
        assert isinstance(refs[0], ToolResult)
        assert refs[0].tool_use_id == "toolu_abc"
        assert refs[0].is_error is False
        assert len(refs[0].content) == 1
        assert isinstance(refs[0].content[0], TextRef)
        # Verify nested text was stored
        text = await content_store.get_text(refs[0].content[0].content_block_id)
        assert text == "sunny, 72°F"

    async def test_tool_result_with_image(self, content_store, asset_store):
        raw = b"screenshot-png"
        b64 = base64.b64encode(raw).decode()
        blocks = [
            NousToolResultContent(
                tool_use_id="toolu_def",
                content=[NousImageContent(mime_type="image/png", data=b64)],
            )
        ]

        refs = await nous_to_stored(
            blocks, content_store, asset_store, ContentOrigin.SYSTEM
        )

        assert len(refs) == 1
        result = refs[0]
        assert isinstance(result, ToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], AssetRef)
        assert result.content[0].mime_type == "image/png"

    async def test_tool_result_with_error(self, content_store, asset_store):
        blocks = [
            NousToolResultContent(
                tool_use_id="toolu_err",
                content=[NousTextContent(text="command failed")],
                is_error=True,
            )
        ]

        refs = await nous_to_stored(
            blocks, content_store, asset_store, ContentOrigin.SYSTEM
        )

        assert len(refs) == 1
        assert isinstance(refs[0], ToolResult)
        assert refs[0].is_error is True

    async def test_tool_result_empty_content(self, content_store, asset_store):
        blocks = [
            NousToolResultContent(
                tool_use_id="toolu_empty",
                content=[],
                is_error=False,
            )
        ]

        refs = await nous_to_stored(
            blocks, content_store, asset_store, ContentOrigin.SYSTEM
        )

        assert len(refs) == 1
        result = refs[0]
        assert isinstance(result, ToolResult)
        assert result.content == ()

    async def test_multiple_blocks_mixed(self, content_store, asset_store):
        raw = b"img"
        b64 = base64.b64encode(raw).decode()
        blocks = [
            NousTextContent(text="thinking..."),
            NousToolUseContent(id="c1", name="calc", input={"x": 1}),
            NousImageContent(mime_type="image/png", data=b64),
        ]

        refs = await nous_to_stored(
            blocks, content_store, asset_store, ContentOrigin.ASSISTANT
        )

        assert len(refs) == 3
        assert isinstance(refs[0], TextRef)
        assert isinstance(refs[1], ToolCall)
        assert isinstance(refs[2], AssetRef)

    async def test_empty_blocks_returns_empty(self, content_store, asset_store):
        refs = await nous_to_stored(
            [], content_store, asset_store, ContentOrigin.USER
        )
        assert refs == []

    async def test_each_asset_gets_unique_entity_id(self, content_store, asset_store):
        """Storing two images should create two distinct assets."""
        b64_a = base64.b64encode(b"image-a").decode()
        b64_b = base64.b64encode(b"image-b").decode()
        blocks = [
            NousImageContent(mime_type="image/png", data=b64_a),
            NousImageContent(mime_type="image/jpeg", data=b64_b),
        ]

        refs = await nous_to_stored(
            blocks, content_store, asset_store, ContentOrigin.ASSISTANT
        )

        assert len(refs) == 2
        assert refs[0].asset_id != refs[1].asset_id


# ---------------------------------------------------------------------------
# Round-trip tests: stored → nous → stored
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """Tests verifying data survives nous ↔ mneme round-trips."""

    async def test_text_round_trip(self, content_store, asset_store):
        # Store original text
        cid = await content_store.store_text("round trip", ContentOrigin.USER)
        original = [TextRef(content_block_id=cid)]

        # mneme → nous
        nous_blocks = await stored_to_nous(original, content_store, asset_store)
        assert len(nous_blocks) == 1
        assert nous_blocks[0].text == "round trip"

        # nous → mneme
        stored = await nous_to_stored(
            nous_blocks, content_store, asset_store, ContentOrigin.USER
        )
        assert len(stored) == 1
        assert isinstance(stored[0], TextRef)

        # Verify the new ref resolves to the same text
        text = await content_store.get_text(stored[0].content_block_id)
        assert text == "round trip"

    async def test_image_round_trip(self, content_store, asset_store):
        raw = b"\x89PNG\r\n\x1a\nreal-image-data-here"
        aid = await asset_store.store_asset(EntityId.generate(), raw, "image/png")
        original = [AssetRef(asset_id=aid, mime_type="image/png")]

        # mneme → nous
        nous_blocks = await stored_to_nous(original, content_store, asset_store)
        assert len(nous_blocks) == 1
        assert isinstance(nous_blocks[0], NousImageContent)

        # nous → mneme
        stored = await nous_to_stored(
            nous_blocks, content_store, asset_store, ContentOrigin.ASSISTANT
        )
        assert len(stored) == 1
        assert isinstance(stored[0], AssetRef)

        # Verify binary data survived
        data = await asset_store.get_asset_data(stored[0].asset_id)
        assert data == raw

    async def test_audio_round_trip(self, content_store, asset_store):
        raw = b"RIFF\x00\x00\x00\x00WAVEfmt "
        aid = await asset_store.store_asset(EntityId.generate(), raw, "audio/wav")
        original = [AssetRef(asset_id=aid, mime_type="audio/wav")]

        nous_blocks = await stored_to_nous(original, content_store, asset_store)
        assert isinstance(nous_blocks[0], NousAudioContent)

        stored = await nous_to_stored(
            nous_blocks, content_store, asset_store, ContentOrigin.ASSISTANT
        )
        data = await asset_store.get_asset_data(stored[0].asset_id)
        assert data == raw

    async def test_tool_call_round_trip(self, content_store, asset_store):
        original = [ToolCall(id="c1", name="search", input={"q": "test", "limit": 10})]

        nous_blocks = await stored_to_nous(original, content_store, asset_store)
        assert isinstance(nous_blocks[0], NousToolUseContent)

        stored = await nous_to_stored(
            nous_blocks, content_store, asset_store, ContentOrigin.ASSISTANT
        )
        assert len(stored) == 1
        tc = stored[0]
        assert isinstance(tc, ToolCall)
        assert tc.id == "c1"
        assert tc.name == "search"
        assert tc.input == {"q": "test", "limit": 10}

    async def test_tool_result_round_trip(self, content_store, asset_store):
        cid = await content_store.store_text("result data", ContentOrigin.SYSTEM)
        original = [
            ToolResult(
                tool_use_id="c1",
                content=(TextRef(content_block_id=cid),),
                is_error=False,
            )
        ]

        nous_blocks = await stored_to_nous(original, content_store, asset_store)
        assert isinstance(nous_blocks[0], NousToolResultContent)
        assert nous_blocks[0].content[0].text == "result data"

        stored = await nous_to_stored(
            nous_blocks, content_store, asset_store, ContentOrigin.SYSTEM
        )
        assert len(stored) == 1
        tr = stored[0]
        assert isinstance(tr, ToolResult)
        assert tr.tool_use_id == "c1"
        assert tr.is_error is False
        assert len(tr.content) == 1
        text = await content_store.get_text(tr.content[0].content_block_id)
        assert text == "result data"

    async def test_complex_message_round_trip(self, content_store, asset_store):
        """Simulates a full assistant response: text + tool use + tool result."""
        # Build original stored content
        text_cid = await content_store.store_text(
            "Let me search for that.", ContentOrigin.ASSISTANT
        )
        result_cid = await content_store.store_text(
            "Found 3 results", ContentOrigin.SYSTEM
        )
        img_data = b"chart-png-bytes"
        img_aid = await asset_store.store_asset(
            EntityId.generate(), img_data, "image/png"
        )

        original: list[StoredContent] = [
            TextRef(content_block_id=text_cid),
            ToolCall(id="c1", name="search", input={"q": "test"}),
            ToolResult(
                tool_use_id="c1",
                content=(
                    TextRef(content_block_id=result_cid),
                    AssetRef(asset_id=img_aid, mime_type="image/png"),
                ),
                is_error=False,
            ),
        ]

        # Round trip: stored → nous → stored
        nous_blocks = await stored_to_nous(original, content_store, asset_store)
        assert len(nous_blocks) == 3

        stored = await nous_to_stored(
            nous_blocks, content_store, asset_store, ContentOrigin.ASSISTANT
        )
        assert len(stored) == 3

        # Verify structure
        assert isinstance(stored[0], TextRef)
        assert isinstance(stored[1], ToolCall)
        assert isinstance(stored[2], ToolResult)

        # Verify text content
        t = await content_store.get_text(stored[0].content_block_id)
        assert t == "Let me search for that."

        # Verify tool result nested content
        tr = stored[2]
        assert isinstance(tr, ToolResult)
        assert len(tr.content) == 2
        assert isinstance(tr.content[0], TextRef)
        assert isinstance(tr.content[1], AssetRef)

        nested_text = await content_store.get_text(tr.content[0].content_block_id)
        assert nested_text == "Found 3 results"

        nested_img = await asset_store.get_asset_data(tr.content[1].asset_id)
        assert nested_img == img_data
