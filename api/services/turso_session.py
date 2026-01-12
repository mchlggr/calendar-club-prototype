"""
Turso/libsql implementation of the OpenAI Agents SDK Session protocol.

Provides cloud-hosted SQLite database storage for conversation persistence
using Turso's libsql-client. Compatible with the agents SDK Session interface.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import libsql_client

if TYPE_CHECKING:
    from libsql_client import Client

logger = logging.getLogger(__name__)


class TursoSession:
    """
    Turso/libsql implementation of the agents SDK Session protocol.

    Implements the same interface as SQLiteSession but uses Turso's
    libsql-client for cloud-hosted database storage.

    Usage:
        session = TursoSession(
            session_id="user-123",
            url="libsql://your-db.turso.io",
            auth_token="your-token"
        )
        items = await session.get_items()
        await session.add_items([{"role": "user", "content": "Hello"}])
        await session.close()
    """

    def __init__(self, session_id: str, url: str, auth_token: str):
        """
        Initialize a Turso session.

        Args:
            session_id: Unique identifier for the session
            url: Turso database URL (libsql://your-db.turso.io)
            auth_token: Turso authentication token
        """
        self.session_id = session_id
        self._url = url
        self._auth_token = auth_token
        self._client: Client | None = None
        self._schema_initialized = False

    async def _get_client(self) -> Client:
        """
        Get or create the libsql client.

        Lazily initializes the client and ensures schema exists.
        """
        if self._client is None:
            self._client = libsql_client.create_client(
                url=self._url,
                auth_token=self._auth_token,
            )
        if not self._schema_initialized:
            await self._ensure_schema()
            self._schema_initialized = True
        return self._client

    async def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        if self._client is None:
            return

        await self._client.batch(
            [
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
                   ON agent_messages (session_id, created_at)""",
            ]
        )

    async def get_items(self, limit: int | None = None) -> list[dict[str, Any]]:
        """
        Retrieve conversation history.

        Args:
            limit: If specified, return only the latest N items (chronologically)

        Returns:
            List of conversation items in chronological order
        """
        client = await self._get_client()

        if limit is None:
            result = await client.execute(
                "SELECT message_data FROM agent_messages "
                "WHERE session_id = ? ORDER BY created_at ASC",
                [self.session_id],
            )
        else:
            # Get latest N items by selecting DESC then reversing
            result = await client.execute(
                "SELECT message_data FROM agent_messages "
                "WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                [self.session_id, limit],
            )

        items: list[dict[str, Any]] = []
        rows = list(result.rows)

        # Reverse if we fetched with limit (DESC order)
        if limit is not None:
            rows.reverse()

        for row in rows:
            try:
                items.append(json.loads(row["message_data"]))
            except json.JSONDecodeError:
                logger.warning(
                    "Failed to decode message data for session %s", self.session_id
                )
                continue

        return items

    async def add_items(self, items: list[dict[str, Any]]) -> None:
        """
        Add new items to conversation history.

        Args:
            items: List of conversation items to add
        """
        if not items:
            return

        client = await self._get_client()

        # Ensure session exists
        await client.execute(
            "INSERT OR IGNORE INTO agent_sessions (session_id) VALUES (?)",
            [self.session_id],
        )

        # Insert messages
        for item in items:
            await client.execute(
                "INSERT INTO agent_messages (session_id, message_data) VALUES (?, ?)",
                [self.session_id, json.dumps(item)],
            )

        # Update session timestamp
        await client.execute(
            "UPDATE agent_sessions SET updated_at = datetime('now') WHERE session_id = ?",
            [self.session_id],
        )

    async def pop_item(self) -> dict[str, Any] | None:
        """
        Remove and return the most recent item.

        Returns:
            The most recent item, or None if session is empty
        """
        client = await self._get_client()

        # Get the most recent message ID
        result = await client.execute(
            "SELECT id, message_data FROM agent_messages "
            "WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            [self.session_id],
        )

        if not result.rows:
            return None

        row = result.rows[0]
        msg_id = row["id"]

        # Delete it
        await client.execute("DELETE FROM agent_messages WHERE id = ?", [msg_id])

        try:
            return json.loads(row["message_data"])
        except json.JSONDecodeError:
            logger.warning(
                "Failed to decode popped message data for session %s", self.session_id
            )
            return None

    async def clear_session(self) -> None:
        """Clear all items for this session."""
        client = await self._get_client()

        await client.execute(
            "DELETE FROM agent_messages WHERE session_id = ?",
            [self.session_id],
        )
        await client.execute(
            "DELETE FROM agent_sessions WHERE session_id = ?",
            [self.session_id],
        )

    async def close(self) -> None:
        """Close the database connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._schema_initialized = False
