"""SQLite implementation of OAuthConnectionStore."""

from datetime import datetime
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ids import OAuthConnectionId, UserId
from ..structure.oauth_connection import OAuthConnection
from ..structure.protocol import OAuthConnectionStore
from .models import OAuthConnectionModel, datetime_to_epoch_ms, epoch_ms_to_datetime, new_uuid, now_epoch_ms, parse_uuid


class SqliteOAuthConnectionStore(OAuthConnectionStore):
    """SQLite-backed OAuthConnectionStore implementation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _to_domain(self, row: OAuthConnectionModel) -> OAuthConnection:
        return OAuthConnection(
            id=parse_uuid(row.id),
            user_id=parse_uuid(row.user_id),
            provider=row.provider,
            access_token=row.access_token,
            scopes=row.scopes or [],
            refresh_token=row.refresh_token,
            token_expires_at=epoch_ms_to_datetime(row.token_expires_at),
            provider_user_id=row.provider_user_id,
            provider_email=row.provider_email,
            connection_name=row.connection_name,
            metadata=row.provider_metadata,
            is_active=row.is_active,
            created_at=epoch_ms_to_datetime(row.created_at),
            updated_at=epoch_ms_to_datetime(row.updated_at),
            last_used_at=epoch_ms_to_datetime(row.last_used_at),
        )

    def _from_domain(self, conn: OAuthConnection) -> OAuthConnectionModel:
        return OAuthConnectionModel(
            id=str(conn.id),
            user_id=str(conn.user_id),
            provider=conn.provider,
            access_token=conn.access_token,
            scopes=conn.scopes,
            refresh_token=conn.refresh_token,
            token_expires_at=datetime_to_epoch_ms(conn.token_expires_at),
            provider_user_id=conn.provider_user_id,
            provider_email=conn.provider_email,
            connection_name=conn.connection_name,
            provider_metadata=conn.metadata,
            is_active=conn.is_active,
            created_at=datetime_to_epoch_ms(conn.created_at) or now_epoch_ms(),
            updated_at=datetime_to_epoch_ms(conn.updated_at) or now_epoch_ms(),
            last_used_at=datetime_to_epoch_ms(conn.last_used_at),
        )

    async def create_connection(self, connection: OAuthConnection) -> OAuthConnection:
        # Check for existing active connections for this provider+user
        result = await self.db.execute(
            select(OAuthConnectionModel).where(
                and_(
                    OAuthConnectionModel.user_id == str(connection.user_id),
                    OAuthConnectionModel.provider == connection.provider,
                    OAuthConnectionModel.is_active == True,  # noqa: E712
                )
            )
        )
        existing_connections = result.scalars().all()

        if existing_connections:
            # Update the first connection with new tokens, deactivate others
            for i, existing in enumerate(existing_connections):
                if i == 0:
                    existing.access_token = connection.access_token
                    existing.refresh_token = connection.refresh_token
                    existing.token_expires_at = datetime_to_epoch_ms(connection.token_expires_at)
                    existing.scopes = connection.scopes
                    existing.provider_user_id = connection.provider_user_id
                    existing.provider_email = connection.provider_email
                    existing.updated_at = now_epoch_ms()
                    if connection.connection_name:
                        existing.connection_name = connection.connection_name
                    if connection.metadata:
                        existing.provider_metadata = connection.metadata
                    updated_row = existing
                else:
                    existing.is_active = False
                    existing.updated_at = now_epoch_ms()

            await self.db.flush()
            return self._to_domain(updated_row)

        # No existing connection — create new one
        row = self._from_domain(connection)
        self.db.add(row)
        await self.db.flush()
        return connection

    async def get_connection(self, connection_id: OAuthConnectionId) -> Optional[OAuthConnection]:
        result = await self.db.execute(
            select(OAuthConnectionModel).where(
                OAuthConnectionModel.id == str(connection_id)
            )
        )
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def get_user_connections(
        self,
        user_id: UserId,
        provider: Optional[str] = None,
        active_only: bool = True,
    ) -> list[OAuthConnection]:
        conditions = [OAuthConnectionModel.user_id == str(user_id)]

        if provider:
            conditions.append(OAuthConnectionModel.provider == provider)
        if active_only:
            conditions.append(OAuthConnectionModel.is_active == True)  # noqa: E712

        result = await self.db.execute(
            select(OAuthConnectionModel).where(and_(*conditions))
        )
        return [self._to_domain(row) for row in result.scalars()]

    async def get_active_connection(
        self,
        user_id: UserId,
        provider: str,
        required_scopes: Optional[list[str]] = None,
    ) -> Optional[OAuthConnection]:
        connections = await self.get_user_connections(
            user_id=user_id,
            provider=provider,
            active_only=True,
        )

        if required_scopes:
            connections = [
                conn for conn in connections
                if conn.has_all_scopes(required_scopes)
            ]

        return connections[0] if connections else None

    async def update_connection(
        self,
        connection_id: OAuthConnectionId,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        token_expires_at: Optional[datetime] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[OAuthConnection]:
        result = await self.db.execute(
            select(OAuthConnectionModel).where(
                OAuthConnectionModel.id == str(connection_id)
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return None

        if access_token is not None:
            row.access_token = access_token
        if refresh_token is not None:
            row.refresh_token = refresh_token
        if token_expires_at is not None:
            row.token_expires_at = datetime_to_epoch_ms(token_expires_at)
        if is_active is not None:
            row.is_active = is_active

        row.updated_at = now_epoch_ms()
        await self.db.flush()
        return self._to_domain(row)

    async def delete_connection(
        self,
        connection_id: OAuthConnectionId,
        user_id: UserId,
    ) -> bool:
        result = await self.db.execute(
            select(OAuthConnectionModel).where(
                and_(
                    OAuthConnectionModel.id == str(connection_id),
                    OAuthConnectionModel.user_id == str(user_id),
                )
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return False

        await self.db.delete(row)
        await self.db.flush()
        return True

    async def update_last_used(self, connection_id: OAuthConnectionId) -> None:
        result = await self.db.execute(
            select(OAuthConnectionModel).where(
                OAuthConnectionModel.id == str(connection_id)
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.last_used_at = now_epoch_ms()
            await self.db.flush()
