"""SQLite implementation of UCM storage.

Usage:
    from mneme.sqlite import create_stores

    engine = create_engine(Path("data/mneme.db"))
    await init_database(engine)
    session_maker = create_session_maker(engine)

    async with session_maker() as db:
        stores = create_stores(db, storage_root=Path("data/blobs"))
        conv = await stores.conversations.create_conversation(user_id, "Hello")
"""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ..content.blob_storage import BlobStorage
from .asset_store import SqliteAssetStore
from .content_store import SqliteContentStore
from .conversation_store import SqliteConversationStore
from .database import close_database, create_engine, create_session_maker, init_database
from .document_store import SqliteDocumentStore
from .entity_store import SqliteEntityStore
from .mcp_server_store import SqliteMCPServerStore
from .oauth_store import SqliteOAuthConnectionStore
from .user_store import SqliteUserStore


class SqliteStores:
    """Container for all SQLite store implementations sharing one session."""

    def __init__(
        self,
        entities: SqliteEntityStore,
        conversations: SqliteConversationStore,
        documents: SqliteDocumentStore,
        users: SqliteUserStore,
        content: SqliteContentStore,
        assets: SqliteAssetStore,
        mcp_servers: SqliteMCPServerStore,
        oauth_connections: SqliteOAuthConnectionStore,
    ) -> None:
        self.entities = entities
        self.conversations = conversations
        self.documents = documents
        self.users = users
        self.content = content
        self.assets = assets
        self.mcp_servers = mcp_servers
        self.oauth_connections = oauth_connections


def create_stores(db: AsyncSession, storage_root: Path) -> SqliteStores:
    """Create all SQLite stores sharing a single database session.

    Args:
        db: Async SQLAlchemy session (manages transaction lifecycle).
        storage_root: Root directory for binary asset storage.
    """
    blob_storage = BlobStorage(storage_root)
    return SqliteStores(
        entities=SqliteEntityStore(db),
        conversations=SqliteConversationStore(db),
        documents=SqliteDocumentStore(db),
        users=SqliteUserStore(db),
        content=SqliteContentStore(db),
        assets=SqliteAssetStore(db, blob_storage),
        mcp_servers=SqliteMCPServerStore(db),
        oauth_connections=SqliteOAuthConnectionStore(db),
    )


__all__ = [
    "SqliteStores",
    "SqliteEntityStore",
    "SqliteConversationStore",
    "SqliteDocumentStore",
    "SqliteUserStore",
    "SqliteContentStore",
    "SqliteAssetStore",
    "SqliteMCPServerStore",
    "SqliteOAuthConnectionStore",
    "create_stores",
    "create_engine",
    "create_session_maker",
    "init_database",
    "close_database",
]
