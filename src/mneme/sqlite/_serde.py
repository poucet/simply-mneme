"""Serialization helpers for StoredContent ↔ MessageContentModel rows.

Converts between the domain StoredContent types and the message_content
table rows used by the noema database schema. Text content flows through
content_blocks; tool data is stored as JSON in the tool_data column.
"""

import json
from typing import Any

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
from .models import MessageContentModel, new_uuid


def stored_content_to_rows(
    message_id: str,
    items: list[StoredContent],
) -> list[MessageContentModel]:
    """Convert StoredContent list to MessageContentModel rows for insertion."""
    return [
        _item_to_row(message_id, seq, item)
        for seq, item in enumerate(items)
    ]


def rows_to_stored_content(rows: list[MessageContentModel]) -> list[StoredContent]:
    """Convert MessageContentModel rows back to StoredContent list."""
    return [_row_to_item(row) for row in rows]


def _item_to_row(message_id: str, sequence: int, item: StoredContent) -> MessageContentModel:
    match item:
        case TextRef(content_block_id=cid):
            return MessageContentModel(
                id=new_uuid(),
                message_id=message_id,
                sequence_number=sequence,
                content_type="text",
                content_block_id=str(cid),
            )
        case AssetRef(asset_id=aid, mime_type=mt):
            return MessageContentModel(
                id=new_uuid(),
                message_id=message_id,
                sequence_number=sequence,
                content_type="asset_ref",
                asset_id=str(aid),
                mime_type=mt,
            )
        case DocumentRef(document_id=did):
            return MessageContentModel(
                id=new_uuid(),
                message_id=message_id,
                sequence_number=sequence,
                content_type="document_ref",
                document_id=str(did),
            )
        case ToolCall(id=tid, name=name, input=inp):
            return MessageContentModel(
                id=new_uuid(),
                message_id=message_id,
                sequence_number=sequence,
                content_type="tool_call",
                tool_data=json.dumps({"id": tid, "name": name, "input": inp}),
            )
        case ToolResult(tool_call_id=tuid, content=content, is_error=err):
            return MessageContentModel(
                id=new_uuid(),
                message_id=message_id,
                sequence_number=sequence,
                content_type="tool_result",
                tool_data=json.dumps({
                    "tool_call_id": tuid,
                    "content": [_tool_content_to_dict(c) for c in content],
                    "is_error": err,
                }),
            )
        case _:
            raise ValueError(f"Unknown StoredContent type: {type(item)}")


def _row_to_item(row: MessageContentModel) -> StoredContent:
    match row.content_type:
        case "text":
            return TextRef(content_block_id=ContentBlockId(row.content_block_id))
        case "asset_ref":
            return AssetRef(asset_id=AssetId(row.asset_id), mime_type=row.mime_type)
        case "document_ref":
            return DocumentRef(document_id=DocumentId(row.document_id))
        case "tool_call":
            data = json.loads(row.tool_data)
            return ToolCall(id=data["id"], name=data["name"], input=data["input"])
        case "tool_result":
            data = json.loads(row.tool_data)
            return ToolResult(
                tool_call_id=data.get("tool_call_id") or data.get("tool_use_id", ""),
                content=tuple(_dict_to_tool_content(c) for c in data.get("content", [])),
                is_error=data.get("is_error", False),
            )
        case _:
            raise ValueError(f"Unknown content type: {row.content_type}")


def _tool_content_to_dict(item: ToolContent) -> dict[str, Any]:
    match item:
        case TextRef(content_block_id=cid):
            return {"type": "text_ref", "content_block_id": str(cid)}
        case AssetRef(asset_id=aid, mime_type=mt):
            return {"type": "asset_ref", "asset_id": str(aid), "mime_type": mt}
        case _:
            raise ValueError(f"Unknown ToolContent type: {type(item)}")


def _dict_to_tool_content(data: dict[str, Any]) -> ToolContent:
    match data["type"]:
        case "text_ref":
            return TextRef(content_block_id=ContentBlockId(data["content_block_id"]))
        case "asset_ref":
            return AssetRef(asset_id=AssetId(data["asset_id"]), mime_type=data["mime_type"])
        case _:
            raise ValueError(f"Unknown tool content type: {data['type']}")
