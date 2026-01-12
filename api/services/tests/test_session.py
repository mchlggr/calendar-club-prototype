"""Tests for SessionManager hybrid SQLite/Turso support."""

from unittest.mock import patch

import pytest

from api.services.session import SessionManager
from api.services.turso_session import TursoSession


class TestSessionManagerHybrid:
    """Tests for hybrid SQLite/Turso session selection."""

    def test_detects_local_sqlite_path(self):
        """Local file paths use SQLite."""
        manager = SessionManager(db_path="/path/to/conversations.db")
        assert not manager._is_turso

    def test_detects_turso_url(self):
        """libsql:// URLs use Turso."""
        manager = SessionManager(db_path="libsql://my-db.turso.io")
        assert manager._is_turso

    def test_get_session_returns_sqlite_for_local(self):
        """Local path returns SQLiteSession."""
        from agents import SQLiteSession

        manager = SessionManager(db_path="/tmp/test.db")

        session = manager.get_session("user-123")

        assert isinstance(session, SQLiteSession)
        assert session.session_id == "user-123"

    def test_get_session_returns_turso_for_libsql_url(self):
        """libsql:// URL returns TursoSession."""
        with patch("api.services.session.get_settings") as mock_settings:
            mock_settings.return_value.turso_auth_token = "test-token"

            manager = SessionManager(db_path="libsql://my-db.turso.io")

            session = manager.get_session("user-456")

            assert isinstance(session, TursoSession)
            assert session.session_id == "user-456"
            assert session._url == "libsql://my-db.turso.io"
            assert session._auth_token == "test-token"

    @pytest.mark.asyncio
    async def test_clear_session_sqlite(self, tmp_path):
        """Clear session works with SQLite."""
        db_path = tmp_path / "test.db"
        manager = SessionManager(db_path=str(db_path))

        # Create a session and add some data
        session = manager.get_session("to-clear")
        await session.add_items([{"role": "user", "content": "test"}])

        # Verify data exists
        items = await session.get_items()
        assert len(items) == 1

        # Clear it
        await manager.clear_session("to-clear")

        # Verify cleared
        session2 = manager.get_session("to-clear")
        items2 = await session2.get_items()
        assert len(items2) == 0


class TestSessionManagerDefaults:
    """Tests for default database path resolution."""

    def test_uses_env_database_url_if_set(self):
        """DATABASE_URL env var is used when set."""
        with patch("api.services.session.get_settings") as mock_settings:
            mock_settings.return_value.database_url = "libsql://env-db.turso.io"

            manager = SessionManager()

            assert manager.db_path == "libsql://env-db.turso.io"
            assert manager._is_turso

    def test_falls_back_to_local_file(self):
        """No DATABASE_URL falls back to local file."""
        with patch("api.services.session.get_settings") as mock_settings:
            mock_settings.return_value.database_url = ""

            manager = SessionManager()

            assert "conversations.db" in manager.db_path
            assert not manager._is_turso
