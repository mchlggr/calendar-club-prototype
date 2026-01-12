"""
Session management for multi-turn conversation persistence.

Supports both SQLite-based persistence (when DATABASE_URL is set) and
in-memory sessions (graceful fallback when no database is configured).
"""

import logging
from pathlib import Path
from typing import Any, Union

from agents import SQLiteSession

from api.config import get_settings

logger = logging.getLogger(__name__)

# Default database path (relative to api root)
DEFAULT_DB_PATH = Path(__file__).parent.parent / "conversations.db"


class InMemorySession:
    """
    In-memory session implementation for non-persisted mode.

    Implements the same interface as SQLiteSession but stores data
    in memory only. Data is lost when the process restarts.

    This is the fallback when no database is configured.
    """

    # Class-level storage shared across all instances
    _storage: dict[str, list[Any]] = {}

    def __init__(self, session_id: str):
        """
        Initialize an in-memory session.

        Args:
            session_id: Unique identifier for the session
        """
        self.session_id = session_id
        if session_id not in self._storage:
            self._storage[session_id] = []

    async def get_items(self, limit: int | None = None) -> list[Any]:
        """Retrieve conversation history for this session."""
        items = self._storage.get(self.session_id, [])
        if limit is not None:
            return items[-limit:]
        return items.copy()

    async def add_items(self, items: list[Any]) -> None:
        """Add new items to the conversation history."""
        if self.session_id not in self._storage:
            self._storage[self.session_id] = []
        self._storage[self.session_id].extend(items)

    async def pop_item(self) -> Any | None:
        """Remove and return the most recent item."""
        items = self._storage.get(self.session_id, [])
        if items:
            return items.pop()
        return None

    async def clear_session(self) -> None:
        """Clear all items for this session."""
        self._storage[self.session_id] = []

    @classmethod
    def clear_all(cls) -> None:
        """Clear all sessions (useful for testing)."""
        cls._storage.clear()


# Type alias for session return type
Session = Union[SQLiteSession, InMemorySession]


class SessionManager:
    """
    Manages sessions for conversation persistence.

    Automatically falls back to in-memory sessions when no database
    is configured (DATABASE_URL is empty).

    Usage:
        manager = SessionManager()
        session = manager.get_session("user-123")
        # Use session with Runner.run_streamed()
        await manager.clear_session("user-123")
    """

    def __init__(self, db_path: Union[str, Path, None] = None, use_persistence: bool | None = None):
        """
        Initialize the session manager.

        Args:
            db_path: Path to SQLite database file. Defaults to api/conversations.db
            use_persistence: Override persistence setting. If None, checks DATABASE_URL config.
        """
        settings = get_settings()

        if use_persistence is None:
            self._use_persistence = settings.has_database
        else:
            self._use_persistence = use_persistence

        self.db_path = str(db_path or DEFAULT_DB_PATH)

        if self._use_persistence:
            logger.info("Session manager initialized with SQLite persistence: %s", self.db_path)
        else:
            logger.info("Session manager initialized in non-persisted (in-memory) mode")

    @property
    def is_persistent(self) -> bool:
        """Check if sessions are being persisted to database."""
        return self._use_persistence

    def get_session(self, session_id: str) -> Session:
        """
        Get or create a session for the given ID.

        Returns SQLiteSession if database is configured, otherwise InMemorySession.

        Args:
            session_id: Unique identifier for the session (e.g., user ID, device ID)

        Returns:
            Session instance for use with agents
        """
        if self._use_persistence:
            return SQLiteSession(session_id, self.db_path)
        return InMemorySession(session_id)

    async def clear_session(self, session_id: str) -> None:
        """
        Clear all conversation state for a session.

        Use this for the "Reset my tastes" feature to start fresh.

        Args:
            session_id: Session to clear
        """
        session = self.get_session(session_id)
        await session.clear_session()


# Global session manager instance
_session_manager: Union[SessionManager, None] = None


def get_session_manager() -> SessionManager:
    """
    Get the global session manager instance.

    Returns a singleton SessionManager for dependency injection in FastAPI.
    Automatically uses in-memory sessions if DATABASE_URL is not set.

    Example:
        @app.post("/chat")
        async def chat(
            request: ChatRequest,
            manager: SessionManager = Depends(get_session_manager)
        ):
            session = manager.get_session(request.session_id)
            ...
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def init_session_manager(
    db_path: Union[str, Path, None] = None,
    use_persistence: bool | None = None,
) -> SessionManager:
    """
    Initialize the global session manager with custom settings.

    Call this at application startup if you need a custom database path
    or want to explicitly enable/disable persistence.

    Args:
        db_path: Custom path for the SQLite database
        use_persistence: Override persistence setting

    Returns:
        The initialized SessionManager
    """
    global _session_manager
    _session_manager = SessionManager(db_path=db_path, use_persistence=use_persistence)
    return _session_manager
