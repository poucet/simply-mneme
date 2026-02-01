"""SQLite implementation of ConversationStore."""

from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..structure.protocol import ConversationStore
from ..ids import ConversationId, EntityId, SpanId, TurnId, UserId
from ..types import EntityType, RelationType, Role
from ..content.stored import StoredContent
from ..addressable.entity import Entity
from ..structure.conversation import (
    Conversation,
    Message,
    MessageWithContent,
    Span,
    Turn,
    TurnWithContent,
)
from .models import (
    ConversationSelectionModel,
    EntityModel,
    EntityRelationModel,
    MessageContentModel,
    MessageModel,
    SpanModel,
    TurnModel,
    epoch_ms_to_datetime,
    new_uuid,
    now_epoch_ms,
)
from ._serde import rows_to_stored_content, stored_content_to_rows


class SqliteConversationStore(ConversationStore):
    """SQLite-backed ConversationStore implementation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- Conversion helpers --

    def _entity_to_domain(self, row: EntityModel) -> Entity:
        from .entity_store import SqliteEntityStore
        return SqliteEntityStore(self.db)._to_domain(row)

    def _conversation_to_domain(self, entity_row: EntityModel) -> Conversation:
        meta = entity_row.metadata_ or {}
        return Conversation(
            entity=self._entity_to_domain(entity_row),
            system_prompt=meta.get("system_prompt"),
        )

    def _turn_to_domain(self, row: TurnModel) -> Turn:
        return Turn(
            id=TurnId(row.id),
            role=Role(row.role),
            created_at=epoch_ms_to_datetime(row.created_at),
        )

    def _span_to_domain(self, row: SpanModel, message_count: int = 0) -> Span:
        return Span(
            id=SpanId(row.id),
            turn_id=TurnId(row.turn_id),
            model_id=row.model_id,
            message_count=message_count,
            created_at=epoch_ms_to_datetime(row.created_at),
        )

    def _message_to_domain(self, row: MessageModel) -> Message:
        return Message(
            id=row.id,
            span_id=SpanId(row.span_id),
            sequence=row.sequence_number,
            role=Role(row.role),
            created_at=epoch_ms_to_datetime(row.created_at),
        )

    # -- Conversation management --

    async def create_conversation(
        self,
        user_id: UserId,
        title: str,
        system_prompt: Optional[str] = None,
    ) -> Conversation:
        metadata = {}
        if system_prompt is not None:
            metadata["system_prompt"] = system_prompt

        entity_id = new_uuid()
        entity_row = EntityModel(
            id=entity_id,
            entity_type=EntityType.CONVERSATION.value,
            user_id=str(user_id),
            name=title,
            metadata_=metadata or None,
        )
        self.db.add(entity_row)
        await self.db.flush()

        return self._conversation_to_domain(entity_row)

    async def list_conversations(
        self,
        user_id: UserId,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[Conversation]:
        stmt = (
            select(EntityModel)
            .where(
                EntityModel.entity_type == EntityType.CONVERSATION.value,
                EntityModel.user_id == str(user_id),
                EntityModel.is_archived == False,
            )
            .order_by(EntityModel.updated_at.desc())
        )
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        return [
            self._conversation_to_domain(row)
            for row in result.scalars()
        ]

    async def get_conversation(self, conversation_id: ConversationId) -> Optional[Conversation]:
        result = await self.db.execute(
            select(EntityModel).where(
                EntityModel.id == str(conversation_id),
                EntityModel.entity_type == EntityType.CONVERSATION.value,
            )
        )
        entity_row = result.scalar_one_or_none()
        if entity_row is None:
            return None
        return self._conversation_to_domain(entity_row)

    async def update_conversation(
        self,
        conversation_id: ConversationId,
        system_prompt: Optional[str] = None,
    ) -> Conversation:
        result = await self.db.execute(
            select(EntityModel).where(
                EntityModel.id == str(conversation_id),
                EntityModel.entity_type == EntityType.CONVERSATION.value,
            )
        )
        entity_row = result.scalar_one()

        if system_prompt is not None:
            meta = dict(entity_row.metadata_ or {})
            meta["system_prompt"] = system_prompt
            entity_row.metadata_ = meta

        entity_row.updated_at = now_epoch_ms()
        await self.db.flush()
        return self._conversation_to_domain(entity_row)

    async def delete_conversation(self, conversation_id: ConversationId) -> bool:
        await self.db.execute(
            delete(ConversationSelectionModel)
            .where(ConversationSelectionModel.conversation_id == str(conversation_id))
        )
        await self.db.execute(
            delete(EntityModel).where(EntityModel.id == str(conversation_id))
        )
        await self.db.flush()
        return True

    # -- Turn / Span / Message --

    async def create_turn(self, role: Role) -> Turn:
        row = TurnModel(id=new_uuid(), role=role.value)
        self.db.add(row)
        await self.db.flush()
        return self._turn_to_domain(row)

    async def get_turn(self, turn_id: TurnId) -> Optional[Turn]:
        result = await self.db.execute(
            select(TurnModel).where(TurnModel.id == str(turn_id))
        )
        row = result.scalar_one_or_none()
        return self._turn_to_domain(row) if row else None

    async def create_span(
        self,
        turn_id: TurnId,
        model_id: Optional[str] = None,
    ) -> Span:
        row = SpanModel(
            id=new_uuid(),
            turn_id=str(turn_id),
            model_id=model_id,
        )
        self.db.add(row)
        await self.db.flush()
        return self._span_to_domain(row, message_count=0)

    async def get_spans(self, turn_id: TurnId) -> list[Span]:
        # Compute message_count dynamically via subquery (matches noema pattern)
        msg_count = (
            select(func.count())
            .where(MessageModel.span_id == SpanModel.id)
            .correlate(SpanModel)
            .scalar_subquery()
            .label("message_count")
        )
        result = await self.db.execute(
            select(SpanModel, msg_count).where(SpanModel.turn_id == str(turn_id))
        )
        return [
            self._span_to_domain(row, message_count=count)
            for row, count in result.all()
        ]

    async def add_message(
        self,
        span_id: SpanId,
        role: Role,
        content: list[StoredContent],
    ) -> Message:
        # Get current message count for sequence number
        result = await self.db.execute(
            select(func.count()).select_from(MessageModel).where(
                MessageModel.span_id == str(span_id)
            )
        )
        sequence = result.scalar()

        msg_id = new_uuid()
        row = MessageModel(
            id=msg_id,
            span_id=str(span_id),
            sequence_number=sequence,
            role=role.value,
        )
        self.db.add(row)
        await self.db.flush()

        # Insert content rows into message_content table
        content_rows = stored_content_to_rows(msg_id, content)
        for cr in content_rows:
            self.db.add(cr)
        if content_rows:
            await self.db.flush()

        return self._message_to_domain(row)

    async def get_messages(self, span_id: SpanId) -> list[Message]:
        result = await self.db.execute(
            select(MessageModel)
            .where(MessageModel.span_id == str(span_id))
            .order_by(MessageModel.sequence_number)
        )
        return [self._message_to_domain(row) for row in result.scalars()]

    async def get_message_content(self, message_id: str) -> list[StoredContent]:
        """Load content for a single message from the message_content table."""
        result = await self.db.execute(
            select(MessageContentModel)
            .where(MessageContentModel.message_id == message_id)
            .order_by(MessageContentModel.sequence_number)
        )
        return rows_to_stored_content(list(result.scalars()))

    # -- Selection management --

    async def select_span(
        self,
        conversation_id: ConversationId,
        turn_id: TurnId,
        span_id: SpanId,
    ) -> None:
        result = await self.db.execute(
            select(ConversationSelectionModel).where(
                ConversationSelectionModel.conversation_id == str(conversation_id),
                ConversationSelectionModel.turn_id == str(turn_id),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.span_id = str(span_id)
        else:
            pos_result = await self.db.execute(
                select(func.coalesce(func.max(ConversationSelectionModel.sequence_number), -1))
                .where(ConversationSelectionModel.conversation_id == str(conversation_id))
            )
            next_pos = pos_result.scalar() + 1

            row = ConversationSelectionModel(
                conversation_id=str(conversation_id),
                turn_id=str(turn_id),
                span_id=str(span_id),
                sequence_number=next_pos,
            )
            self.db.add(row)

        await self.db.flush()

    async def get_selected_span(
        self,
        conversation_id: ConversationId,
        turn_id: TurnId,
    ) -> Optional[SpanId]:
        result = await self.db.execute(
            select(ConversationSelectionModel.span_id).where(
                ConversationSelectionModel.conversation_id == str(conversation_id),
                ConversationSelectionModel.turn_id == str(turn_id),
            )
        )
        span_id = result.scalar_one_or_none()
        return SpanId(span_id) if span_id else None

    # -- Path queries --

    async def get_conversation_path(self, conversation_id: ConversationId) -> list[TurnWithContent]:
        """Get the full conversation path (all selected turns + messages)."""
        sel_result = await self.db.execute(
            select(ConversationSelectionModel)
            .where(ConversationSelectionModel.conversation_id == str(conversation_id))
            .order_by(ConversationSelectionModel.sequence_number)
        )
        selections = list(sel_result.scalars())
        if not selections:
            return []

        # Batch-load turns and spans
        turn_ids = [s.turn_id for s in selections]
        span_ids = [s.span_id for s in selections]

        turn_result = await self.db.execute(
            select(TurnModel).where(TurnModel.id.in_(turn_ids))
        )
        turns_by_id = {r.id: r for r in turn_result.scalars()}

        span_result = await self.db.execute(
            select(SpanModel).where(SpanModel.id.in_(span_ids))
        )
        spans_by_id = {r.id: r for r in span_result.scalars()}

        # Batch-load messages for all selected spans
        msg_result = await self.db.execute(
            select(MessageModel)
            .where(MessageModel.span_id.in_(span_ids))
            .order_by(MessageModel.span_id, MessageModel.sequence_number)
        )
        messages_by_span: dict[str, list[MessageModel]] = {}
        for msg in msg_result.scalars():
            messages_by_span.setdefault(msg.span_id, []).append(msg)

        # Batch-load all message content
        all_message_ids = [
            msg.id
            for msgs in messages_by_span.values()
            for msg in msgs
        ]
        content_by_message: dict[str, list[MessageContentModel]] = {}
        if all_message_ids:
            content_result = await self.db.execute(
                select(MessageContentModel)
                .where(MessageContentModel.message_id.in_(all_message_ids))
                .order_by(MessageContentModel.message_id, MessageContentModel.sequence_number)
            )
            for row in content_result.scalars():
                content_by_message.setdefault(row.message_id, []).append(row)

        # Assemble in selection order
        path = []
        for sel in selections:
            turn_row = turns_by_id.get(sel.turn_id)
            span_row = spans_by_id.get(sel.span_id)
            if not turn_row or not span_row:
                continue

            msg_rows = messages_by_span.get(sel.span_id, [])
            messages = [
                MessageWithContent(
                    message=self._message_to_domain(m),
                    content=rows_to_stored_content(content_by_message.get(m.id, [])),
                )
                for m in msg_rows
            ]

            path.append(TurnWithContent(
                turn=self._turn_to_domain(turn_row),
                span=self._span_to_domain(span_row, message_count=len(msg_rows)),
                messages=messages,
            ))

        return path

    async def get_context_at(
        self,
        conversation_id: ConversationId,
        up_to_turn_id: TurnId,
    ) -> list[TurnWithContent]:
        """Get conversation path up to (and including) a specific turn."""
        full_path = await self.get_conversation_path(conversation_id)
        result = []
        for twc in full_path:
            result.append(twc)
            if str(twc.turn.id) == str(up_to_turn_id):
                break
        return result

    # -- Branching --

    async def fork_conversation(
        self,
        conversation_id: ConversationId,
        at_turn_id: TurnId,
    ) -> Conversation:
        """Fork a conversation at a specific turn."""
        original = await self.get_conversation(conversation_id)

        metadata = {}
        if original.system_prompt is not None:
            metadata["system_prompt"] = original.system_prompt

        entity_id = new_uuid()
        entity_row = EntityModel(
            id=entity_id,
            entity_type=EntityType.CONVERSATION.value,
            user_id=str(original.entity.user_id) if original.entity.user_id else None,
            name=original.entity.name,
            metadata_=metadata or None,
        )
        self.db.add(entity_row)
        await self.db.flush()

        # Copy selections up to the fork point
        new_conv_id = ConversationId(entity_id)
        await self.copy_selections(conversation_id, new_conv_id, at_turn_id, include_turn=True)

        # Track fork via entity relation
        relation_row = EntityRelationModel(
            from_id=entity_id,
            to_id=str(conversation_id),
            relation=RelationType.FORKED_FROM.value,
            metadata_={"at_turn_id": str(at_turn_id)},
        )
        self.db.add(relation_row)
        await self.db.flush()

        return self._conversation_to_domain(entity_row)

    async def copy_selections(
        self,
        from_conversation_id: ConversationId,
        to_conversation_id: ConversationId,
        up_to_turn_id: TurnId,
        include_turn: bool = False,
    ) -> int:
        """Copy selections from one conversation to another, up to a given turn."""
        sel_result = await self.db.execute(
            select(ConversationSelectionModel)
            .where(ConversationSelectionModel.conversation_id == str(from_conversation_id))
            .order_by(ConversationSelectionModel.sequence_number)
        )
        copied = 0
        for sel in sel_result.scalars():
            if not include_turn and sel.turn_id == str(up_to_turn_id):
                break

            new_sel = ConversationSelectionModel(
                conversation_id=str(to_conversation_id),
                turn_id=sel.turn_id,
                span_id=sel.span_id,
                sequence_number=copied,
            )
            self.db.add(new_sel)
            copied += 1

            if sel.turn_id == str(up_to_turn_id):
                break

        await self.db.flush()
        return copied

    async def get_turn_count(self, conversation_id: ConversationId) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(ConversationSelectionModel)
            .where(ConversationSelectionModel.conversation_id == str(conversation_id))
        )
        return result.scalar()
