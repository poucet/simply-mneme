"""Content bridge: nous inline content ↔ mneme stored references.

Mneme stores content as references (TextRef, AssetRef, ToolCall, ToolResult).
Nous expects inline content (TextContent, ImageContent, ToolUseContent, etc.).

This bridge resolves refs → inline on read, and stores inline → refs on write.

Requires the 'nous' optional dependency: pip install simply-mneme[nous]
"""

import base64

from nous.types.content import (
    AudioContent as NousAudioContent,
    ContentBlock as NousContentBlock,
    ImageContent as NousImageContent,
    TextContent as NousTextContent,
    ToolContent as NousToolContent,
    ToolResultContent as NousToolResultContent,
    ToolUseContent as NousToolUseContent,
)

from ..ids import EntityId
from ..types import ContentOrigin
from .protocol import AssetStore, ContentStore
from .stored import (
    AssetRef,
    DocumentRef,
    StoredContent,
    TextRef,
    ToolCall,
    ToolContent,
    ToolResult,
)


async def stored_to_nous(
    refs: list[StoredContent],
    content_store: ContentStore,
    asset_store: AssetStore,
) -> list[NousContentBlock]:
    """Resolve mneme StoredContent refs into nous inline ContentBlocks.

    TextRef    → resolve text from ContentStore → NousTextContent
    AssetRef   → resolve binary from AssetStore → NousImageContent or NousAudioContent
    ToolCall   → NousToolUseContent
    ToolResult → resolve nested content → NousToolResultContent
    DocumentRef → expanded separately by ContentProcessor (skipped here)
    """
    result: list[NousContentBlock] = []

    for ref in refs:
        block = await _resolve_one(ref, content_store, asset_store)
        if block is not None:
            result.append(block)

    return result


async def nous_to_stored(
    blocks: list[NousContentBlock],
    content_store: ContentStore,
    asset_store: AssetStore,
    origin: ContentOrigin,
    model_id: str | None = None,
) -> list[StoredContent]:
    """Store nous inline ContentBlocks as mneme StoredContent refs.

    NousTextContent       → store text in ContentStore → TextRef
    NousImageContent      → store asset in AssetStore  → AssetRef
    NousAudioContent      → store asset in AssetStore  → AssetRef
    NousToolUseContent    → ToolCall (no storage needed, inline frozen dataclass)
    NousToolResultContent → resolve nested content → ToolResult
    """
    result: list[StoredContent] = []

    for block in blocks:
        ref = await _store_one(block, content_store, asset_store, origin, model_id)
        if ref is not None:
            result.append(ref)

    return result


# ---------------------------------------------------------------------------
# Internal: resolve one ref → one nous block
# ---------------------------------------------------------------------------

async def _resolve_one(
    ref: StoredContent,
    content_store: ContentStore,
    asset_store: AssetStore,
) -> NousContentBlock | None:
    match ref:
        case TextRef(content_block_id=cid):
            text = await content_store.get_text(cid)
            if text is None:
                return None
            return NousTextContent(text=text)

        case AssetRef(asset_id=aid, mime_type=mt):
            data = await asset_store.get_asset_data(aid)
            if data is None:
                return None
            b64 = base64.b64encode(data).decode("ascii")
            if mt.startswith("audio/"):
                return NousAudioContent(mime_type=mt, data=b64, attachment_id=str(aid))
            return NousImageContent(mime_type=mt, data=b64, attachment_id=str(aid))

        case DocumentRef():
            # Document expansion is handled separately by ContentProcessor.
            return None

        case ToolCall(id=tid, name=name, input=inp):
            return NousToolUseContent(id=tid, name=name, input=inp)

        case ToolResult(tool_use_id=tuid, content=content, is_error=err):
            nested: list[NousToolContent] = []
            for item in content:
                resolved = await _resolve_one(item, content_store, asset_store)
                if resolved is not None:
                    nested.append(resolved)
            return NousToolResultContent(
                tool_use_id=tuid,
                content=nested,
                is_error=err,
            )

        case _:
            return None


# ---------------------------------------------------------------------------
# Internal: store one nous block → one ref
# ---------------------------------------------------------------------------

async def _store_one(
    block: NousContentBlock,
    content_store: ContentStore,
    asset_store: AssetStore,
    origin: ContentOrigin,
    model_id: str | None,
) -> StoredContent | None:
    match block:
        case NousTextContent(text=text):
            cid = await content_store.store_text(text, origin, model_id=model_id)
            return TextRef(content_block_id=cid)

        case NousImageContent(mime_type=mt, data=data):
            return await _store_asset(mt, data, asset_store)

        case NousAudioContent(mime_type=mt, data=data):
            return await _store_asset(mt, data, asset_store)

        case NousToolUseContent(id=tid, name=name, input=inp):
            return ToolCall(id=tid, name=name, input=inp)

        case NousToolResultContent(tool_use_id=tuid, content=content, is_error=err):
            nested: list[ToolContent] = []
            for item in content:
                stored = await _store_one(item, content_store, asset_store, origin, model_id)
                if stored is not None and isinstance(stored, (TextRef, AssetRef)):
                    nested.append(stored)
            return ToolResult(
                tool_use_id=tuid,
                content=tuple(nested),
                is_error=err,
            )

        case _:
            return None


async def _store_asset(
    mime_type: str,
    data: str | None,
    asset_store: AssetStore,
) -> AssetRef | None:
    if not data:
        return None
    binary = base64.b64decode(data)
    new_aid = await asset_store.store_asset(
        entity_id=EntityId.generate(),
        data=binary,
        mime_type=mime_type,
    )
    return AssetRef(asset_id=new_aid, mime_type=mime_type)
