"""Serialization helpers for StoredContent ↔ JSON.

Used to store StoredContent lists in the messages.content JSON column.
"""

from typing import Any
from uuid import UUID

from ..ids import AssetId, ContentBlockId, DocumentId
from ..content.stored import (
    AssetRef,
    DocumentRef,
    StoredContent,
    TextRef,
    ToolCall,
    ToolContent,
    ToolResult,
)


def serialize_content(items: list[StoredContent]) -> list[dict[str, Any]]:
    """Convert StoredContent list to JSON-serializable dicts."""
    return [_serialize_item(item) for item in items]


def deserialize_content(data: list[dict[str, Any]]) -> list[StoredContent]:
    """Convert JSON dicts back to StoredContent list."""
    return [_deserialize_item(item) for item in data]


def _serialize_item(item: StoredContent) -> dict[str, Any]:
    match item:
        case TextRef(content_block_id=cid):
            return {"type": "text_ref", "content_block_id": str(cid)}
        case AssetRef(asset_id=aid, mime_type=mt):
            return {"type": "asset_ref", "asset_id": str(aid), "mime_type": mt}
        case DocumentRef(document_id=did):
            return {"type": "document_ref", "document_id": str(did)}
        case ToolCall(id=tid, name=name, input=inp):
            return {"type": "tool_call", "id": tid, "name": name, "input": inp}
        case ToolResult(tool_use_id=tuid, content=content, is_error=err):
            return {
                "type": "tool_result",
                "tool_use_id": tuid,
                "content": [_serialize_tool_content(c) for c in content],
                "is_error": err,
            }
        case _:
            raise ValueError(f"Unknown StoredContent type: {type(item)}")


def _serialize_tool_content(item: ToolContent) -> dict[str, Any]:
    match item:
        case TextRef(content_block_id=cid):
            return {"type": "text_ref", "content_block_id": str(cid)}
        case AssetRef(asset_id=aid, mime_type=mt):
            return {"type": "asset_ref", "asset_id": str(aid), "mime_type": mt}
        case _:
            raise ValueError(f"Unknown ToolContent type: {type(item)}")


def _deserialize_tool_content(data: dict[str, Any]) -> ToolContent:
    match data["type"]:
        case "text_ref":
            return TextRef(content_block_id=ContentBlockId(data["content_block_id"]))
        case "asset_ref":
            return AssetRef(asset_id=AssetId(data["asset_id"]), mime_type=data["mime_type"])
        case _:
            raise ValueError(f"Unknown tool content type: {data['type']}")


_DESERIALIZERS = {
    "text_ref": lambda d: TextRef(content_block_id=ContentBlockId(d["content_block_id"])),
    "asset_ref": lambda d: AssetRef(asset_id=AssetId(d["asset_id"]), mime_type=d["mime_type"]),
    "document_ref": lambda d: DocumentRef(document_id=DocumentId(d["document_id"])),
    "tool_call": lambda d: ToolCall(id=d["id"], name=d["name"], input=d["input"]),
    "tool_result": lambda d: ToolResult(
        tool_use_id=d["tool_use_id"],
        content=tuple(_deserialize_tool_content(c) for c in d.get("content", [])),
        is_error=d.get("is_error", False),
    ),
}


def _deserialize_item(data: dict[str, Any]) -> StoredContent:
    content_type = data["type"]
    deserializer = _DESERIALIZERS.get(content_type)
    if deserializer is None:
        raise ValueError(f"Unknown content type: {content_type}")
    return deserializer(data)
