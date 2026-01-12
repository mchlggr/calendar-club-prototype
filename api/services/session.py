"""
Session management for multi-turn conversation persistence.

Uses OpenAI Agents SDK's SQLiteSession for local storage, or TursoSession
for cloud-hosted Turso/libsql databases.

Configuration:
- Local SQLite: Leave DATABASE_URL empty (uses api/conversations.db)
- Turso: Set DATABASE_URL=libsql://your-db.turso.io and TURSO_AUTH_TOKEN
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from agents import SQLiteSession

from api.config import get_settings
from api.services.turso_session import TursoSession

# Default database path (relative to api root)
DEFAULT_DB_PATH = Path(__file__).parent.parent / "conversations.db"


def _get_database_path() -> str:
    """
    Get the database path from config or fall back to local file.

    Returns DATABASE_URL if configured, otherwise the default local path.
    For Turso URLs (libsql://...), the agents SDK must support libsql.
    """
    settings = get_settings()
    if settings.database_url:
        return settings.database_url
    return str(DEFAULT_DB_PATH)


class SessionManager:
    """
    Manages sessions for conversation persistence.

    Automatically selects SQLiteSession for local databases or TursoSession
    for Turso/libsql cloud databases based on DATABASE_URL configuration.

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
            db_path: Path to SQLite database file or Turso URL.
                     Defaults to DATABASE_URL env var, or api/conversations.db if not set.
        """
        self.db_path = str(db_path) if db_path else _get_database_path()
        self._is_turso = self.db_path.startswith("libsql://")

    def get_session(self, session_id: str) -> SQLiteSession | TursoSession:
        """
        Get or create a session for the given ID.

        Returns TursoSession for Turso URLs (libsql://...), otherwise SQLiteSession.

        Args:
            session_id: Unique identifier for the session (e.g., user ID, device ID)

        Returns:
            Session instance for use with agents (SQLiteSession or TursoSession)
        """
        if self._is_turso:
            settings = get_settings()
            return TursoSession(
                session_id=session_id,
                url=self.db_path,
                auth_token=settings.turso_auth_token,
            )
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
