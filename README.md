# mneme

Storage layer implementing the Unified Content Model (UCM) for [noema](https://github.com/poucet/noema). Mneme provides persistent, content-addressed storage for conversations, documents, and assets using a three-layer architecture.

## Architecture

Mneme organizes storage into three layers:

**Addressable** — Identity and relationships. Every conversation, document, and asset is an `Entity` with a unified ID, naming, privacy, and archival. Directed relationships (`FORKED_FROM`, `REFERENCES`, `DERIVED_FROM`, `GROUPED_WITH`) link entities together.

**Structure** — Domain hierarchy. Conversations follow a `Conversation → Turn → Span → Message` path that supports branching and forking. Documents use a `Document → Tab → Revision` hierarchy with immutable snapshots.

**Content** — Immutable, deduplicated storage. Text blocks and binary assets are stored separately from structure. Blobs use SHA-256 content addressing with a sharded filesystem layout.

## Installation

```bash
pip install simply-mneme
```

With [nous](https://github.com/poucet/simply-nous) integration:

```bash
pip install simply-mneme[nous]
```

Requires Python 3.12+.

## Quick Start

```python
from mneme.sqlite import create_engine, create_session_maker, init_database, create_stores

engine = create_engine("sqlite+aiosqlite:///mneme.db")
session_maker = create_session_maker(engine)

async with session_maker() as session:
    await init_database(engine)
    stores = create_stores(session)

    # Create a conversation entity
    entity = await stores.entity.create_entity(
        type=EntityType.CONVERSATION,
        user_id=user_id,
        name="My Conversation",
    )
```

## Dependencies

- [SQLAlchemy](https://www.sqlalchemy.org/) (async) — database ORM and engine
- [aiosqlite](https://github.com/omnilib/aiosqlite) — async SQLite driver
- [aiofiles](https://github.com/Tinche/aiofiles) — async file I/O for blob storage

## License

[MIT](LICENSE)
