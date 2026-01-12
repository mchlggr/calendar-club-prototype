"""
SQLite-based session management for multi-turn conversation persistence.

Uses OpenAI Agents SDK's SQLiteSession for storing conversation state,
search profiles, and user preferences across chat turns.
"""

from pathlib import Path
from typing import Union

from agents import SQLiteSession

# Default database path (relative to api root)
DEFAULT_DB_PATH = Path(__file__).parent.parent / "conversations.db"


class SessionManager:
    """
    Manages SQLite sessions for conversation persistence.

    Usage:
        manager = SessionManager()
        session = manager.get_session("user-123")
        # Use session with Runner.run_streamed()
        await manager.clear_session("user-123")
    """

    def __init__(self, db_path: Union[str, Path, None] = None):
        """
        Initialize the session manager.

        Args:
            db_path: Path to SQLite database file. Defaults to api/conversations.db
        """
        self.db_path = str(db_path or DEFAULT_DB_PATH)

    def get_session(self, session_id: str) -> SQLiteSession:
        """
        Get or create a session for the given ID.

        The session persists conversation history and can be used with
        the OpenAI Agents SDK Runner.

        Args:
            session_id: Unique identifier for the session (e.g., user ID, device ID)

        Returns:
            SQLiteSession instance for use with agents
        """
        return SQLiteSession(session_id, self.db_path)

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


def init_session_manager(db_path: Union[str, Path, None] = None) -> SessionManager:
    """
    Initialize the global session manager with custom settings.

    Call this at application startup if you need a custom database path.

    Args:
        db_path: Custom path for the SQLite database

    Returns:
        The initialized SessionManager
    """
    global _session_manager
    _session_manager = SessionManager(db_path=db_path)
    return _session_manager
