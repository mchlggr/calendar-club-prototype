---
date: 2026-01-12T17:16:43Z
researcher: Claude
git_commit: 8e4a333
branch: main
repository: calendar-club-prototype
topic: "TursoSession Implementation Feasibility Assessment"
tags: [research, database, turso, libsql, session, agents-sdk]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude
---

# Research: TursoSession Implementation Feasibility Assessment

**Date**: 2026-01-12T17:16:43Z
**Git Commit**: 8e4a333
**Branch**: main

## Research Question

How hard would it be to implement Option B: Full Turso integration - creating a custom TursoSession class that implements the Session protocol from the OpenAI agents SDK?

## Executive Summary

**Verdict: EASIER THAN EXPECTED (~2-3 hours, not 4-6)**

Key discovery: **libsql-client has native async support**, eliminating the need for `asyncio.to_thread()` bridges. The implementation is straightforward:

| Aspect | Complexity | Notes |
|--------|------------|-------|
| Session Protocol | Simple | 4 async methods + 1 attribute |
| Database Schema | Simple | 2 tables, ~10 columns total |
| libsql-client API | Clean | Native async, similar to sqlite3 |
| Total LOC | ~100-120 | Based on SQLiteSession as template |

---

## Session Protocol Interface

**Location**: `.venv/.../agents/memory/session.py:10-50`

The Session protocol is **runtime-checkable** (structural typing) with:

### Required Attribute
```python
session_id: str
```

### Required Methods (all async)

```python
async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
    """Retrieve conversation history. If limit, return latest N items chronologically."""

async def add_items(self, items: list[TResponseInputItem]) -> None:
    """Add new items to conversation history."""

async def pop_item(self) -> TResponseInputItem | None:
    """Remove and return most recent item, or None if empty."""

async def clear_session(self) -> None:
    """Clear all items for this session."""
```

### Type Definition
`TResponseInputItem` = `ResponseInputItemParam` from OpenAI SDK - represents messages, tool calls, etc.

---

## SQLiteSession Reference Implementation

**Location**: `.venv/.../agents/memory/sqlite_session.py` (~275 lines)

### Database Schema

```sql
-- Sessions table
CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Messages table
CREATE TABLE IF NOT EXISTS agent_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    message_data TEXT NOT NULL,  -- JSON serialized
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES agent_sessions (session_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_session_created ON agent_messages (session_id, created_at);
```

### Key Implementation Patterns

1. **JSON Serialization**: Messages stored as `json.dumps(item)`, parsed with `json.loads()`
2. **Thread Safety**: Uses locks for in-memory DB, thread-local connections for file
3. **Sync-to-Async Bridge**: Uses `asyncio.to_thread()` to wrap sync sqlite3 operations
4. **Upsert Pattern**: `INSERT OR IGNORE` for sessions, `INSERT` for messages
5. **Atomic Pop**: `DELETE ... RETURNING` for `pop_item()`

---

## libsql-client Python API

### Critical Finding: Native Async Support

```python
import libsql_client

# Async client (what we'll use)
async with libsql_client.create_client(
    url="libsql://your-database.turso.io",
    auth_token=os.environ.get("TURSO_AUTH_TOKEN")
) as client:
    result = await client.execute("SELECT * FROM users WHERE id = ?", [user_id])
    for row in result.rows:
        print(row["name"])
```

### API Comparison

| Operation | sqlite3 | libsql_client |
|-----------|---------|---------------|
| Connect | `sqlite3.connect(path)` | `libsql_client.create_client(url, auth_token=)` |
| Execute | `cursor.execute(sql, params)` | `await client.execute(sql, params)` |
| Fetch all | `cursor.fetchall()` | `result.rows` (list) |
| Row access | `row[0]` or `row["col"]` | `row[0]` or `row["col"]` |
| Commit | `conn.commit()` | Automatic (or use transactions) |
| Close | `conn.close()` | `client.close()` or context manager |

### ResultSet Properties
- `result.columns` - tuple of column names
- `result.rows` - list of Row objects
- `result.rows_affected` - for INSERT/UPDATE/DELETE

---

## Implementation Plan

### TursoSession Class (~100-120 lines)

```python
# api/services/turso_session.py

import json
import libsql_client
from typing import Any

class TursoSession:
    """Turso/libsql implementation of agents SDK Session protocol."""

    def __init__(self, session_id: str, url: str, auth_token: str):
        self.session_id = session_id
        self._url = url
        self._auth_token = auth_token
        self._client: libsql_client.Client | None = None

    async def _get_client(self) -> libsql_client.Client:
        """Lazy client initialization."""
        if self._client is None:
            self._client = libsql_client.create_client(
                url=self._url,
                auth_token=self._auth_token
            )
            await self._ensure_schema()
        return self._client

    async def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        client = await self._get_client()
        await client.batch([
            """CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )""",
            """CREATE TABLE IF NOT EXISTS agent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_data TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES agent_sessions(session_id)
                    ON DELETE CASCADE
            )""",
            """CREATE INDEX IF NOT EXISTS idx_session_created
               ON agent_messages (session_id, created_at)"""
        ])

    async def get_items(self, limit: int | None = None) -> list[dict[str, Any]]:
        client = await self._get_client()
        if limit is None:
            result = await client.execute(
                "SELECT message_data FROM agent_messages WHERE session_id = ? ORDER BY created_at ASC",
                [self.session_id]
            )
        else:
            result = await client.execute(
                "SELECT message_data FROM agent_messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                [self.session_id, limit]
            )
            # Reverse to chronological order
            result.rows.reverse()

        items = []
        for row in result.rows:
            try:
                items.append(json.loads(row["message_data"]))
            except json.JSONDecodeError:
                continue
        return items

    async def add_items(self, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        client = await self._get_client()

        # Ensure session exists
        await client.execute(
            "INSERT OR IGNORE INTO agent_sessions (session_id) VALUES (?)",
            [self.session_id]
        )

        # Insert messages
        for item in items:
            await client.execute(
                "INSERT INTO agent_messages (session_id, message_data) VALUES (?, ?)",
                [self.session_id, json.dumps(item)]
            )

        # Update session timestamp
        await client.execute(
            "UPDATE agent_sessions SET updated_at = datetime('now') WHERE session_id = ?",
            [self.session_id]
        )

    async def pop_item(self) -> dict[str, Any] | None:
        client = await self._get_client()

        # Get the most recent message ID
        result = await client.execute(
            "SELECT id, message_data FROM agent_messages WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            [self.session_id]
        )

        if not result.rows:
            return None

        row = result.rows[0]
        msg_id = row["id"]

        # Delete it
        await client.execute(
            "DELETE FROM agent_messages WHERE id = ?",
            [msg_id]
        )

        try:
            return json.loads(row["message_data"])
        except json.JSONDecodeError:
            return None

    async def clear_session(self) -> None:
        client = await self._get_client()
        await client.execute(
            "DELETE FROM agent_messages WHERE session_id = ?",
            [self.session_id]
        )
        await client.execute(
            "DELETE FROM agent_sessions WHERE session_id = ?",
            [self.session_id]
        )

    async def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
```

### SessionManager Integration

```python
# api/services/session.py (modified)

from agents import SQLiteSession
from api.services.turso_session import TursoSession

class SessionManager:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path) if db_path else _get_database_path()
        self._is_turso = self.db_path.startswith("libsql://")

    def get_session(self, session_id: str) -> SQLiteSession | TursoSession:
        if self._is_turso:
            settings = get_settings()
            return TursoSession(
                session_id,
                url=self.db_path,
                auth_token=settings.turso_auth_token
            )
        return SQLiteSession(session_id, self.db_path)
```

---

## Effort Breakdown

| Task | Time Estimate |
|------|--------------|
| Create `TursoSession` class | 1 hour |
| Modify `SessionManager` | 15 min |
| Add `libsql-client` dependency | 5 min |
| Write unit tests | 45 min |
| Integration testing | 30 min |
| **Total** | **~2.5 hours** |

### Why Lower Than Original Estimate

1. **Native async** - No need for `asyncio.to_thread()` wrapper complexity
2. **Simple schema** - Only 2 tables, well-defined structure
3. **Clean API** - libsql-client API is similar to sqlite3
4. **Reference impl** - SQLiteSession provides exact patterns to follow

---

## Risks and Considerations

### Low Risk
- **Schema compatibility**: Same schema as SQLiteSession, no migration needed
- **API stability**: libsql-client is actively maintained by Turso

### Medium Risk
- **Network latency**: Remote DB adds latency vs local SQLite
- **Connection management**: May need connection pooling for production

### Mitigation
- Batch operations where possible (schema creation uses `client.batch()`)
- Consider lazy initialization pattern (already in design)
- Add retry logic for network failures (future enhancement)

---

## Alternative: Hybrid Approach

If you want both local SQLite and remote Turso support:

```python
def get_session(self, session_id: str) -> SQLiteSession | TursoSession:
    settings = get_settings()

    if settings.database_url.startswith("libsql://"):
        return TursoSession(session_id, settings.database_url, settings.turso_auth_token)
    elif settings.database_url:
        return SQLiteSession(session_id, settings.database_url)
    else:
        return SQLiteSession(session_id, str(DEFAULT_DB_PATH))
```

This lets you:
- Local dev: No `DATABASE_URL` → uses local `conversations.db`
- Production: `DATABASE_URL=libsql://...` → uses Turso

---

## Code References

- `.venv/.../agents/memory/session.py:10-50` - Session protocol definition
- `.venv/.../agents/memory/sqlite_session.py:13` - SQLiteSession implementation
- `api/services/session.py:35-69` - Current SessionManager
- `api/index.py:298-303` - Session usage in chat endpoint

## External Documentation

- [Turso Python SDK Quickstart](https://docs.turso.tech/sdk/python/quickstart)
- [libsql-client-py GitHub](https://github.com/tursodatabase/libsql-client-py)
- [OpenAI Agents SDK Memory](https://github.com/openai/agents-sdk/tree/main/agents/memory)
