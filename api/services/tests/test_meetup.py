"""Tests for the Meetup GraphQL client."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.meetup import MeetupClient, MeetupEvent, get_meetup_client


class TestMeetupEventModel:
    """Tests for MeetupEvent model."""

    def test_create_meetup_event_minimal(self):
        """Test creating a MeetupEvent with required fields."""
        event = MeetupEvent(
            id="meetup:test123",
            title="Test Meetup Event",
            description="A test event description",
            start_time=datetime.now(UTC),
        )
        assert event.id == "meetup:test123"
        assert event.title == "Test Meetup Event"
        assert event.description == "A test event description"
        assert event.is_free is True  # Default
        assert event.category == "community"  # Default

    def test_create_meetup_event_all_fields(self):
        """Test creating a MeetupEvent with all optional fields."""
        now = datetime.now(UTC)
        event = MeetupEvent(
            id="meetup:456",
            title="Full Meetup Event",
            description="A complete event description",
            start_time=now,
            end_time=now + timedelta(hours=2),
            venue_name="Tech Hub Columbus",
            venue_address="123 Main St, Columbus, OH",
            category="tech",
            is_free=False,
            price_amount=10,
            url="https://meetup.com/events/456",
            image_url="https://example.com/image.jpg",
            group_name="Columbus Tech Meetup",
        )
        assert event.venue_name == "Tech Hub Columbus"
        assert event.venue_address == "123 Main St, Columbus, OH"
        assert event.is_free is False
        assert event.price_amount == 10
        assert event.group_name == "Columbus Tech Meetup"
        assert event.url == "https://meetup.com/events/456"


class TestMeetupClientInit:
    """Tests for MeetupClient initialization."""

    def test_client_init_no_token(self):
        """Test client initialization without token."""
        with patch("api.services.meetup.get_settings") as mock_settings:
            mock_settings.return_value.meetup_access_token = ""
            client = MeetupClient()
            assert client.access_token == ""

    def test_client_init_with_token(self):
        """Test client initialization with token."""
        client = MeetupClient(access_token="test_token")
        assert client.access_token == "test_token"


class TestMeetupClientParseEvent:
    """Tests for MeetupClient._parse_event method."""

    @pytest.fixture
    def client(self):
        """Create a MeetupClient for testing."""
        return MeetupClient(access_token="test_token")

    def test_parse_event_basic(self, client):
        """Test parsing a basic event."""
        data = {
            "id": "123",
            "title": "Python Meetup",
            "description": "Learn Python together",
            "dateTime": "2026-01-15T18:00:00-05:00",
            "eventUrl": "https://meetup.com/events/123",
        }
        event = client._parse_event(data)
        assert event is not None
        assert event.id == "123"
        assert event.title == "Python Meetup"
        assert event.description == "Learn Python together"
        assert event.url == "https://meetup.com/events/123"

    def test_parse_event_with_venue(self, client):
        """Test parsing an event with venue information."""
        data = {
            "id": "456",
            "title": "Tech Talk",
            "description": "Monthly tech discussion",
            "dateTime": "2026-01-20T19:00:00Z",
            "venue": {
                "name": "Innovation Hub",
                "address": "456 Tech Ave",
                "city": "Columbus",
                "state": "OH",
            },
        }
        event = client._parse_event(data)
        assert event is not None
        assert event.venue_name == "Innovation Hub"
        assert "456 Tech Ave" in event.venue_address
        assert "Columbus" in event.venue_address
        assert "OH" in event.venue_address

    def test_parse_event_with_fee(self, client):
        """Test parsing an event with fee settings."""
        data = {
            "id": "789",
            "title": "Workshop",
            "description": "Hands-on workshop",
            "dateTime": "2026-01-25T10:00:00-05:00",
            "feeSettings": {
                "amount": 25,
                "currency": "USD",
                "required": True,
            },
        }
        event = client._parse_event(data)
        assert event is not None
        assert event.is_free is False
        assert event.price_amount == 25

    def test_parse_event_free(self, client):
        """Test parsing a free event."""
        data = {
            "id": "101",
            "title": "Free Meetup",
            "description": "Free community event",
            "dateTime": "2026-01-30T18:00:00-05:00",
            "feeSettings": None,
        }
        event = client._parse_event(data)
        assert event is not None
        assert event.is_free is True
        assert event.price_amount is None

    def test_parse_event_with_group(self, client):
        """Test parsing an event with group information."""
        data = {
            "id": "202",
            "title": "AI Study Group",
            "description": "Weekly AI discussion",
            "dateTime": "2026-02-01T17:00:00-05:00",
            "group": {
                "name": "Columbus AI",
                "urlname": "columbus-ai",
            },
        }
        event = client._parse_event(data)
        assert event is not None
        assert event.group_name == "Columbus AI"

    def test_parse_event_with_image(self, client):
        """Test parsing an event with image."""
        data = {
            "id": "303",
            "title": "Photo Walk",
            "description": "Urban photography meetup",
            "dateTime": "2026-02-05T09:00:00-05:00",
            "images": [
                {"baseUrl": "https://example.com/event-image.jpg"},
            ],
        }
        event = client._parse_event(data)
        assert event is not None
        assert event.image_url == "https://example.com/event-image.jpg"

    def test_parse_event_missing_datetime(self, client):
        """Test parsing an event without datetime returns None."""
        data = {
            "id": "404",
            "title": "Invalid Event",
            "description": "This event has no datetime",
        }
        event = client._parse_event(data)
        assert event is None

    def test_parse_event_with_end_time(self, client):
        """Test parsing an event with end time."""
        data = {
            "id": "505",
            "title": "Long Event",
            "description": "Multi-hour event",
            "dateTime": "2026-02-10T14:00:00-05:00",
            "endTime": "2026-02-10T18:00:00-05:00",
        }
        event = client._parse_event(data)
        assert event is not None
        assert event.end_time is not None
        assert event.end_time > event.start_time


class TestMeetupClientSearchEvents:
    """Tests for MeetupClient.search_events method."""

    @pytest.fixture
    def client(self):
        """Create a MeetupClient for testing."""
        return MeetupClient(access_token="test_token")

    @pytest.mark.asyncio
    async def test_search_events_no_token(self):
        """Test search_events returns empty list without token."""
        client = MeetupClient(access_token="")
        events = await client.search_events()
        assert events == []

    @pytest.mark.asyncio
    async def test_search_events_success(self, client):
        """Test successful event search."""
        mock_result = {
            "rankedEvents": {
                "count": 2,
                "edges": [
                    {
                        "node": {
                            "id": "1",
                            "title": "Event 1",
                            "description": "First event",
                            "dateTime": "2026-01-15T18:00:00-05:00",
                            "eventUrl": "https://meetup.com/1",
                        }
                    },
                    {
                        "node": {
                            "id": "2",
                            "title": "Event 2",
                            "description": "Second event",
                            "dateTime": "2026-01-16T19:00:00-05:00",
                            "eventUrl": "https://meetup.com/2",
                        }
                    },
                ],
            }
        }

        # Mock the GraphQL client session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_client_instance = MagicMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)

        with patch.object(client, "_get_client", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_client_instance

            events = await client.search_events(query="tech", limit=10)

            assert len(events) == 2
            assert events[0].title == "Event 1"
            assert events[1].title == "Event 2"

    @pytest.mark.asyncio
    async def test_search_events_empty_result(self, client):
        """Test search with empty results."""
        mock_result = {
            "rankedEvents": {
                "count": 0,
                "edges": [],
            }
        }

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_client_instance = MagicMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)

        with patch.object(client, "_get_client", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_client_instance

            events = await client.search_events()

            assert events == []

    @pytest.mark.asyncio
    async def test_search_events_handles_exception(self, client):
        """Test search handles exceptions gracefully."""
        with patch.object(client, "_get_client", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("API Error")

            events = await client.search_events()

            assert events == []


class TestGetMeetupClient:
    """Tests for get_meetup_client singleton."""

    def test_get_meetup_client_returns_client(self):
        """Test that get_meetup_client returns a MeetupClient instance."""
        with patch("api.services.meetup._client", None):
            client = get_meetup_client()
            assert isinstance(client, MeetupClient)

    def test_get_meetup_client_returns_same_instance(self):
        """Test that get_meetup_client returns the same instance."""
        with patch("api.services.meetup._client", None):
            client1 = get_meetup_client()
            client2 = get_meetup_client()
            assert client1 is client2
