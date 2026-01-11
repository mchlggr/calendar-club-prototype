"""
SSE Connection Manager for pushing events to active sessions.

Tracks active streaming connections so background tasks can push
events (like 'more_events' from Websets) to specific sessions.
"""

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SSEConnection:
    """Represents an active SSE connection."""

    session_id: str
    queue: asyncio.Queue[dict] = field(default_factory=asyncio.Queue)
    active: bool = True


class SSEConnectionManager:
    """Manages active SSE connections for pushing background events."""

    def __init__(self) -> None:
        self._connections: dict[str, SSEConnection] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str) -> SSEConnection:
        """Register a new SSE connection for a session."""
        async with self._lock:
            # Close existing connection if any
            if session_id in self._connections:
                old_conn = self._connections[session_id]
                old_conn.active = False

            conn = SSEConnection(session_id=session_id)
            self._connections[session_id] = conn
            logger.debug("Registered SSE connection for session: %s", session_id)
            return conn

    async def unregister(self, session_id: str) -> None:
        """Unregister an SSE connection."""
        async with self._lock:
            if session_id in self._connections:
                self._connections[session_id].active = False
                del self._connections[session_id]
                logger.debug("Unregistered SSE connection for session: %s", session_id)

    async def push_event(self, session_id: str, event: dict) -> bool:
        """Push an event to a session's queue.

        Args:
            session_id: The session to push to
            event: Event dict with 'type' and other fields

        Returns:
            True if event was pushed, False if session not found
        """
        async with self._lock:
            conn = self._connections.get(session_id)
            if conn and conn.active:
                await conn.queue.put(event)
                logger.debug("Pushed event to session %s: %s", session_id, event.get("type"))
                return True
            return False

    def get_connection(self, session_id: str) -> SSEConnection | None:
        """Get a connection by session ID."""
        return self._connections.get(session_id)

    def has_connection(self, session_id: str) -> bool:
        """Check if a session has an active connection."""
        conn = self._connections.get(session_id)
        return conn is not None and conn.active


# Singleton instance
_manager: SSEConnectionManager | None = None


def get_sse_manager() -> SSEConnectionManager:
    """Get the singleton SSE connection manager."""
    global _manager
    if _manager is None:
        _manager = SSEConnectionManager()
    return _manager
