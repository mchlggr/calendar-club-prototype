"""
Session management for conversation state.

Uses SQLiteSession from OpenAI Agents SDK for persistence.
"""

from pathlib import Path

from agents import SQLiteSession

# Default database path
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "conversations.db"


class SessionManager:
    """Manage conversation sessions with SQLite backing."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)

    def get_session(self, session_id: str) -> SQLiteSession:
        """Get or create a session for the given ID."""
        return SQLiteSession(session_id, self.db_path)

    async def clear_session(self, session_id: str) -> None:
        """Clear a session (for 'Reset my tastes' feature)."""
        session = self.get_session(session_id)
        await session.clear_session()


# Default session manager instance
session_manager = SessionManager()
