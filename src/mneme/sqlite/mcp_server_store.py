"""SQLite implementation of MCPServerStore."""

from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ids import MCPServerId
from ..structure.mcp_server import MCPServer
from ..structure.protocol import MCPServerStore
from .models import MCPServerModel, epoch_ms_to_datetime, new_uuid, now_epoch_ms, parse_uuid


class SqliteMCPServerStore(MCPServerStore):
    """SQLite-backed MCPServerStore implementation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _to_domain(self, row: MCPServerModel) -> MCPServer:
        return MCPServer(
            id=parse_uuid(row.id),
            name=row.name,
            url=row.url,
            enabled=row.enabled,
            headers=row.headers,
            approval_mode=row.approval_mode,
            auto_approve_tools=row.auto_approve_tools or [],
            settings=row.settings or {},
            created_at=epoch_ms_to_datetime(row.created_at),
            updated_at=epoch_ms_to_datetime(row.updated_at),
        )

    async def get_server(self, server_id: MCPServerId) -> Optional[MCPServer]:
        result = await self.db.execute(
            select(MCPServerModel).where(MCPServerModel.id == str(server_id))
        )
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def get_server_by_name(self, name: str) -> Optional[MCPServer]:
        result = await self.db.execute(
            select(MCPServerModel).where(MCPServerModel.name == name)
        )
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list_servers(self, enabled_only: bool = False) -> list[MCPServer]:
        stmt = select(MCPServerModel).order_by(MCPServerModel.name)
        if enabled_only:
            stmt = stmt.where(MCPServerModel.enabled == True)  # noqa: E712
        result = await self.db.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def create_server(
        self,
        name: str,
        url: str,
        enabled: bool = True,
        headers: Optional[dict[str, str]] = None,
        approval_mode: str = "manual",
        auto_approve_tools: Optional[list[str]] = None,
        settings: Optional[dict[str, Any]] = None,
    ) -> MCPServer:
        row = MCPServerModel(
            id=new_uuid(),
            name=name,
            url=url,
            enabled=enabled,
            headers=headers,
            approval_mode=approval_mode,
            auto_approve_tools=auto_approve_tools or [],
            settings=settings or {},
        )
        self.db.add(row)
        await self.db.flush()
        return self._to_domain(row)

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
    ) -> MCPServer:
        result = await self.db.execute(
            select(MCPServerModel).where(MCPServerModel.id == str(server_id))
        )
        row = result.scalar_one()

        if name is not None:
            row.name = name
        if url is not None:
            row.url = url
        if enabled is not None:
            row.enabled = enabled
        if headers is not None:
            row.headers = headers
        if approval_mode is not None:
            row.approval_mode = approval_mode
        if auto_approve_tools is not None:
            row.auto_approve_tools = auto_approve_tools
        if settings is not None:
            row.settings = settings

        row.updated_at = now_epoch_ms()
        await self.db.flush()
        return self._to_domain(row)

    async def delete_server(self, server_id: MCPServerId) -> bool:
        result = await self.db.execute(
            delete(MCPServerModel).where(MCPServerModel.id == str(server_id))
        )
        await self.db.flush()
        return result.rowcount > 0
