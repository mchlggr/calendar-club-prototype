"""Tests for TursoSession."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.turso_session import TursoSession


@pytest.fixture
def mock_client():
    """Create a mock libsql client."""
    client = MagicMock()
    client.execute = AsyncMock()
    client.batch = AsyncMock()
    client.close = MagicMock()
    return client


@pytest.fixture
def session(mock_client):
    """Create a TursoSession with mocked client."""
    with patch("api.services.turso_session.libsql_client") as mock_libsql:
        mock_libsql.create_client.return_value = mock_client
        sess = TursoSession(
            session_id="test-session",
            url="libsql://test.turso.io",
            auth_token="test-token",
        )
        yield sess


class TestTursoSessionInit:
    """Tests for TursoSession initialization."""

    def test_init_stores_config(self):
        """Session stores configuration without connecting."""
        session = TursoSession(
            session_id="my-session",
            url="libsql://my-db.turso.io",
            auth_token="my-token",
        )
        assert session.session_id == "my-session"
        assert session._url == "libsql://my-db.turso.io"
        assert session._auth_token == "my-token"
        assert session._client is None

    def test_init_lazy_connection(self):
        """Client is not created until first use."""
        session = TursoSession(
            session_id="lazy-session",
            url="libsql://lazy.turso.io",
            auth_token="lazy-token",
        )
        assert session._client is None
        assert session._schema_initialized is False


class TestTursoSessionGetClient:
    """Tests for lazy client initialization."""

    @pytest.mark.asyncio
    async def test_get_client_creates_client(self, mock_client):
        """First call creates client and initializes schema."""
        with patch("api.services.turso_session.libsql_client") as mock_libsql:
            mock_libsql.create_client.return_value = mock_client

            session = TursoSession(
                session_id="test",
                url="libsql://test.turso.io",
                auth_token="token",
            )

            client = await session._get_client()

            assert client is mock_client
            mock_libsql.create_client.assert_called_once_with(
                url="libsql://test.turso.io",
                auth_token="token",
            )
            mock_client.batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_client_reuses_client(self, mock_client):
        """Subsequent calls reuse existing client."""
        with patch("api.services.turso_session.libsql_client") as mock_libsql:
            mock_libsql.create_client.return_value = mock_client

            session = TursoSession(
                session_id="test",
                url="libsql://test.turso.io",
                auth_token="token",
            )

            await session._get_client()
            await session._get_client()
            await session._get_client()

            # Client created only once
            mock_libsql.create_client.assert_called_once()
            # Schema initialized only once
            assert mock_client.batch.call_count == 1


class TestTursoSessionGetItems:
    """Tests for get_items method."""

    @pytest.mark.asyncio
    async def test_get_items_empty(self, mock_client):
        """Empty session returns empty list."""
        mock_result = MagicMock()
        mock_result.rows = []
        mock_client.execute.return_value = mock_result

        with patch("api.services.turso_session.libsql_client") as mock_libsql:
            mock_libsql.create_client.return_value = mock_client

            session = TursoSession(
                session_id="empty", url="libsql://test.io", auth_token="token"
            )

            items = await session.get_items()

            assert items == []

    @pytest.mark.asyncio
    async def test_get_items_returns_parsed_json(self, mock_client):
        """Items are parsed from JSON."""
        mock_result = MagicMock()
        mock_result.rows = [
            {"message_data": '{"role": "user", "content": "Hello"}'},
            {"message_data": '{"role": "assistant", "content": "Hi"}'},
        ]
        mock_client.execute.return_value = mock_result

        with patch("api.services.turso_session.libsql_client") as mock_libsql:
            mock_libsql.create_client.return_value = mock_client

            session = TursoSession(
                session_id="test", url="libsql://test.io", auth_token="token"
            )

            items = await session.get_items()

            assert len(items) == 2
            assert items[0] == {"role": "user", "content": "Hello"}
            assert items[1] == {"role": "assistant", "content": "Hi"}

    @pytest.mark.asyncio
    async def test_get_items_with_limit(self, mock_client):
        """Limit parameter returns latest N items in chronological order."""
        mock_result = MagicMock()
        # DESC order from DB (newest first)
        mock_result.rows = [
            {"message_data": '{"content": "newest"}'},
            {"message_data": '{"content": "older"}'},
        ]
        mock_client.execute.return_value = mock_result

        with patch("api.services.turso_session.libsql_client") as mock_libsql:
            mock_libsql.create_client.return_value = mock_client

            session = TursoSession(
                session_id="test", url="libsql://test.io", auth_token="token"
            )

            items = await session.get_items(limit=2)

            # Should be reversed to chronological (oldest first)
            assert items[0] == {"content": "older"}
            assert items[1] == {"content": "newest"}

    @pytest.mark.asyncio
    async def test_get_items_skips_invalid_json(self, mock_client):
        """Invalid JSON is skipped with warning."""
        mock_result = MagicMock()
        mock_result.rows = [
            {"message_data": '{"valid": true}'},
            {"message_data": "not-json"},
            {"message_data": '{"also_valid": true}'},
        ]
        mock_client.execute.return_value = mock_result

        with patch("api.services.turso_session.libsql_client") as mock_libsql:
            mock_libsql.create_client.return_value = mock_client

            session = TursoSession(
                session_id="test", url="libsql://test.io", auth_token="token"
            )

            items = await session.get_items()

            assert len(items) == 2


class TestTursoSessionAddItems:
    """Tests for add_items method."""

    @pytest.mark.asyncio
    async def test_add_items_empty_list(self, mock_client):
        """Empty list does nothing."""
        with patch("api.services.turso_session.libsql_client") as mock_libsql:
            mock_libsql.create_client.return_value = mock_client

            session = TursoSession(
                session_id="test", url="libsql://test.io", auth_token="token"
            )

            await session.add_items([])

            # Should not call execute for inserts
            assert not mock_client.execute.called

    @pytest.mark.asyncio
    async def test_add_items_inserts_messages(self, mock_client):
        """Items are inserted as JSON."""
        with patch("api.services.turso_session.libsql_client") as mock_libsql:
            mock_libsql.create_client.return_value = mock_client

            session = TursoSession(
                session_id="test-session", url="libsql://test.io", auth_token="token"
            )

            await session.add_items([{"role": "user", "content": "Hello"}])

            # Should call execute for: session upsert, message insert, timestamp update
            calls = mock_client.execute.call_args_list
            # Verify session upsert
            assert "INSERT OR IGNORE INTO agent_sessions" in calls[0][0][0]
            # Verify message insert
            assert "INSERT INTO agent_messages" in calls[1][0][0]
            # Verify timestamp update
            assert "UPDATE agent_sessions SET updated_at" in calls[2][0][0]


class TestTursoSessionPopItem:
    """Tests for pop_item method."""

    @pytest.mark.asyncio
    async def test_pop_item_empty_session(self, mock_client):
        """Empty session returns None."""
        mock_result = MagicMock()
        mock_result.rows = []
        mock_client.execute.return_value = mock_result

        with patch("api.services.turso_session.libsql_client") as mock_libsql:
            mock_libsql.create_client.return_value = mock_client

            session = TursoSession(
                session_id="empty", url="libsql://test.io", auth_token="token"
            )

            item = await session.pop_item()

            assert item is None

    @pytest.mark.asyncio
    async def test_pop_item_returns_and_deletes(self, mock_client):
        """Pop returns most recent item and deletes it."""
        mock_result = MagicMock()
        mock_result.rows = [{"id": 42, "message_data": '{"content": "last"}'}]
        mock_client.execute.return_value = mock_result

        with patch("api.services.turso_session.libsql_client") as mock_libsql:
            mock_libsql.create_client.return_value = mock_client

            session = TursoSession(
                session_id="test", url="libsql://test.io", auth_token="token"
            )

            item = await session.pop_item()

            assert item == {"content": "last"}
            # Verify delete was called
            delete_call = mock_client.execute.call_args_list[-1]
            assert "DELETE FROM agent_messages WHERE id" in delete_call[0][0]


class TestTursoSessionClearSession:
    """Tests for clear_session method."""

    @pytest.mark.asyncio
    async def test_clear_session_deletes_all(self, mock_client):
        """Clear deletes messages and session."""
        with patch("api.services.turso_session.libsql_client") as mock_libsql:
            mock_libsql.create_client.return_value = mock_client

            session = TursoSession(
                session_id="to-clear", url="libsql://test.io", auth_token="token"
            )

            await session.clear_session()

            calls = mock_client.execute.call_args_list
            # Should delete messages first
            assert "DELETE FROM agent_messages WHERE session_id" in calls[0][0][0]
            # Then delete session
            assert "DELETE FROM agent_sessions WHERE session_id" in calls[1][0][0]


class TestTursoSessionClose:
    """Tests for close method."""

    @pytest.mark.asyncio
    async def test_close_closes_client(self, mock_client):
        """Close closes the client connection."""
        with patch("api.services.turso_session.libsql_client") as mock_libsql:
            mock_libsql.create_client.return_value = mock_client

            session = TursoSession(
                session_id="test", url="libsql://test.io", auth_token="token"
            )

            # Initialize client first
            await session._get_client()
            assert session._client is not None

            await session.close()

            mock_client.close.assert_called_once()
            assert session._client is None
            assert session._schema_initialized is False

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self):
        """Close is safe when not connected."""
        session = TursoSession(
            session_id="test", url="libsql://test.io", auth_token="token"
        )

        # Should not raise
        await session.close()
