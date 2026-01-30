"""SQLite implementation of UserStore."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ids import UserId
from ..structure.protocol import UserStore
from ..structure.user import User
from .models import UserModel, epoch_ms_to_datetime, new_uuid, now_epoch_ms, parse_uuid


class SqliteUserStore(UserStore):
    """SQLite-backed UserStore implementation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _to_domain(self, row: UserModel) -> User:
        return User(
            id=parse_uuid(row.id),
            email=row.email,
            created_at=epoch_ms_to_datetime(row.created_at),
            updated_at=epoch_ms_to_datetime(row.updated_at),
        )

    async def get_user(self, user_id: UserId) -> Optional[User]:
        result = await self.db.execute(
            select(UserModel).where(UserModel.id == str(user_id))
        )
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def get_user_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(
            select(UserModel).where(UserModel.email == email)
        )
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def create_user(self, email: str) -> User:
        row = UserModel(
            id=new_uuid(),
            email=email,
        )
        self.db.add(row)
        await self.db.flush()
        return self._to_domain(row)

    async def get_or_create_user(self, email: str) -> User:
        existing = await self.get_user_by_email(email)
        if existing is not None:
            return existing
        return await self.create_user(email)

    async def update_user(
        self,
        user_id: UserId,
        email: Optional[str] = None,
    ) -> User:
        result = await self.db.execute(
            select(UserModel).where(UserModel.id == str(user_id))
        )
        row = result.scalar_one()

        if email is not None:
            row.email = email

        row.updated_at = now_epoch_ms()
        await self.db.flush()
        return self._to_domain(row)
