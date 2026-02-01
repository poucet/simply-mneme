"""Store media from tool results as mneme assets.

Bridges nous tool results with mneme asset storage.
Requires simply-nous: install with `pip install simply-mneme[nous]`.
"""

import base64
import logging

from nous.types import ImageContent, AudioContent, ToolResult
from ..ids import EntityId
from .protocol import AssetStore

logger = logging.getLogger(__name__)

_EXT_MAP = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "audio/wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/ogg": "ogg",
    "audio/webm": "webm",
}


async def store_media_from_result(
    result: ToolResult,
    tool_name: str,
    asset_store: AssetStore,
) -> None:
    """Store media content from a tool result as assets.

    Inspects each content item in the result. For ImageContent or AudioContent
    with base64 data, stores them as mneme assets.

    Args:
        result: nous ToolResult containing content blocks.
        tool_name: Name of the tool that produced the result.
        asset_store: mneme AssetStore for persisting media.
    """
    for item in result.content:
        if isinstance(item, (ImageContent, AudioContent)) and item.data:
            await _store_media_asset(item, tool_name, asset_store)


async def _store_media_asset(
    media,
    tool_name: str,
    asset_store: AssetStore,
) -> None:
    """Store a single media item as a mneme asset."""
    try:
        media_bytes = base64.b64decode(media.data)
        ext = _EXT_MAP.get(media.mime_type, "bin")

        await asset_store.store_asset(
            entity_id=EntityId.generate(),
            data=media_bytes,
            mime_type=media.mime_type,
            original_filename=f"{tool_name}_{media.type}.{ext}",
        )
        logger.info(f"Stored {media.type} asset for tool {tool_name}")
    except Exception as e:
        logger.error(f"Failed to store {media.type} asset: {e}")
