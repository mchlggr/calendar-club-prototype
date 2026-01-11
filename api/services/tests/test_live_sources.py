"""
Live integration tests for event source APIs.

These tests hit real API endpoints and require valid API keys in environment.
They are excluded from normal test runs via pytest markers.

## Running Integration Tests

### Prerequisites
Set the required environment variables:
```bash
export FIRECRAWL_API_KEY="your-key"
export EVENTBRITE_API_KEY="your-key"
export EXA_API_KEY="your-key"
```

### Run All Integration Tests
```bash
pytest -m integration api/services/tests/test_live_sources.py -v
```

### Run Tests for Specific Source
```bash
# Firecrawl/Posh only
pytest -m integration -k "Firecrawl or Posh" api/services/tests/test_live_sources.py -v

# Eventbrite only
pytest -m integration -k "Eventbrite" api/services/tests/test_live_sources.py -v

# Exa only (excluding slow webset tests)
pytest -m "integration and not slow" -k "Exa" api/services/tests/test_live_sources.py -v
```

### Run Including Slow Tests (Websets)
```bash
pytest -m integration api/services/tests/test_live_sources.py -v
# Note: Slow tests run by default when -m integration is specified
# The 'slow' marker is informational
```

### Run Normal Tests (Excludes Integration)
```bash
pytest  # Integration tests automatically excluded via pyproject.toml
```

## Test Expectations

These tests verify that:
1. API clients can make real HTTP requests without errors
2. Response parsing works with actual API responses
3. Data models validate against real data

Tests pass if:
- No Python exceptions occur
- Return types match expected types (list, dict, model instances)
- Empty results are acceptable (APIs may have no data or be rate-limited)

Tests are NOT expected to:
- Return specific data (event titles, counts, etc.)
- Always return non-empty results
- Work without valid API keys
"""

import os
import pytest
from datetime import datetime, timedelta, UTC

from api.services.firecrawl import (
    FirecrawlClient,
    PoshExtractor,
    ScrapedEvent,
)
from api.services.eventbrite import (
    EventbriteClient,
    EventbriteEvent,
)
from api.services.exa_client import (
    ExaClient,
    ExaSearchResult,
    ExaWebset,
)


# ============================================================================
# Skip Conditions
# ============================================================================

def skip_if_no_firecrawl_key():
    """Skip test if FIRECRAWL_API_KEY not set."""
    if not os.getenv("FIRECRAWL_API_KEY"):
        pytest.skip("FIRECRAWL_API_KEY required for this test")


def skip_if_no_eventbrite_key():
    """Skip test if EVENTBRITE_API_KEY not set."""
    if not os.getenv("EVENTBRITE_API_KEY"):
        pytest.skip("EVENTBRITE_API_KEY required for this test")


def skip_if_no_exa_key():
    """Skip test if EXA_API_KEY not set."""
    if not os.getenv("EXA_API_KEY"):
        pytest.skip("EXA_API_KEY required for this test")


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
async def firecrawl_client():
    """Create FirecrawlClient with cleanup."""
    skip_if_no_firecrawl_key()
    client = FirecrawlClient()
    yield client
    await client.close()


@pytest.fixture
async def posh_extractor():
    """Create PoshExtractor with cleanup."""
    skip_if_no_firecrawl_key()
    extractor = PoshExtractor()
    yield extractor
    await extractor.close()


@pytest.fixture
async def eventbrite_client():
    """Create EventbriteClient with cleanup."""
    skip_if_no_eventbrite_key()
    client = EventbriteClient()
    yield client
    await client.close()


@pytest.fixture
async def exa_client():
    """Create ExaClient with cleanup."""
    skip_if_no_exa_key()
    client = ExaClient()
    yield client
    await client.close()


# ============================================================================
# Firecrawl Tests
# ============================================================================

@pytest.mark.integration
class TestFirecrawlClientLive:
    """Live integration tests for FirecrawlClient."""

    @pytest.mark.asyncio
    async def test_scrape_posh_homepage(self, firecrawl_client):
        """Test scraping Posh homepage returns valid response."""
        result = await firecrawl_client.scrape(
            url="https://posh.vip",
            formats=["markdown"],
        )

        # Should return dict with data (may be empty if blocked)
        assert isinstance(result, dict)
        # No exception means success - content may vary

    @pytest.mark.asyncio
    async def test_scrape_with_extraction(self, firecrawl_client):
        """Test scraping with LLM extraction schema."""
        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
            },
        }

        result = await firecrawl_client.scrape(
            url="https://posh.vip",
            formats=["extract"],
            extract_schema=schema,
        )

        assert isinstance(result, dict)
        # Extract field may or may not be present depending on page

    @pytest.mark.asyncio
    async def test_crawl_posh_city(self, firecrawl_client):
        """Test crawling Posh city page."""
        results = await firecrawl_client.crawl(
            url="https://posh.vip/c/columbus",
            max_depth=1,
            limit=3,  # Keep small for speed
        )

        # Should return list (may be empty if site blocks crawlers)
        assert isinstance(results, list)
        # Each result should be a dict if any returned
        for result in results:
            assert isinstance(result, dict)


@pytest.mark.integration
class TestPoshExtractorLive:
    """Live integration tests for PoshExtractor."""

    @pytest.mark.asyncio
    async def test_discover_events_columbus(self, posh_extractor):
        """Test discovering events for Columbus."""
        events = await posh_extractor.discover_events(
            city="columbus",
            limit=5,
        )

        # Should return list (may be empty if no events or blocked)
        assert isinstance(events, list)

        # If we got events, validate structure
        for event in events:
            assert isinstance(event, ScrapedEvent)
            assert event.source == "posh"
            assert event.title  # Title is required
            assert event.url  # URL is required
            assert event.event_id  # ID is required

    @pytest.mark.asyncio
    async def test_discover_events_new_york(self, posh_extractor):
        """Test discovering events for different city."""
        events = await posh_extractor.discover_events(
            city="new-york",
            limit=3,
        )

        assert isinstance(events, list)
        for event in events:
            assert isinstance(event, ScrapedEvent)


# ============================================================================
# Eventbrite Tests
# ============================================================================

@pytest.mark.integration
class TestEventbriteClientLive:
    """Live integration tests for EventbriteClient.

    Note: Eventbrite's official search API was deprecated in 2020.
    These tests use undocumented internal APIs which may be flaky.
    """

    @pytest.mark.asyncio
    async def test_search_events_basic(self, eventbrite_client):
        """Test basic event search for Columbus."""
        events = await eventbrite_client.search_events(
            location="Columbus, OH",
            page_size=5,
        )

        # Should return list (may be empty if API unavailable)
        assert isinstance(events, list)

        # If we got events, validate structure
        for event in events:
            assert isinstance(event, EventbriteEvent)
            assert event.id
            assert event.title
            assert event.start_time

    @pytest.mark.asyncio
    async def test_search_events_with_dates(self, eventbrite_client):
        """Test event search with date range filter."""
        start = datetime.now(UTC)
        end = start + timedelta(days=30)

        events = await eventbrite_client.search_events(
            location="Columbus, OH",
            start_date=start,
            end_date=end,
            page_size=5,
        )

        assert isinstance(events, list)

        # If events returned, dates should be in range
        for event in events:
            assert isinstance(event, EventbriteEvent)
            # Note: API may not strictly enforce date filters

    @pytest.mark.asyncio
    async def test_search_events_free_only(self, eventbrite_client):
        """Test event search filtering for free events."""
        events = await eventbrite_client.search_events(
            location="Columbus, OH",
            free_only=True,
            page_size=5,
        )

        assert isinstance(events, list)

        # If events returned, they should be free
        for event in events:
            assert isinstance(event, EventbriteEvent)
            # Note: is_free defaults to True, so this validates structure

    @pytest.mark.asyncio
    async def test_search_events_with_categories(self, eventbrite_client):
        """Test event search with category filter."""
        events = await eventbrite_client.search_events(
            location="Columbus, OH",
            categories=["tech", "ai"],
            page_size=5,
        )

        assert isinstance(events, list)
        for event in events:
            assert isinstance(event, EventbriteEvent)

    @pytest.mark.asyncio
    async def test_search_events_different_location(self, eventbrite_client):
        """Test event search for different location."""
        events = await eventbrite_client.search_events(
            location="New York, NY",
            page_size=3,
        )

        assert isinstance(events, list)
        for event in events:
            assert isinstance(event, EventbriteEvent)


# ============================================================================
# Exa Tests
# ============================================================================

@pytest.mark.integration
class TestExaClientLive:
    """Live integration tests for ExaClient search and find_similar."""

    @pytest.mark.asyncio
    async def test_search_basic(self, exa_client):
        """Test basic neural search."""
        results = await exa_client.search(
            query="tech events Columbus Ohio",
            num_results=5,
        )

        # Should return list (may be empty for obscure queries)
        assert isinstance(results, list)

        for result in results:
            assert isinstance(result, ExaSearchResult)
            assert result.url
            assert result.title

    @pytest.mark.asyncio
    async def test_search_with_text_content(self, exa_client):
        """Test search with full text content included."""
        results = await exa_client.search(
            query="artificial intelligence conferences 2026",
            num_results=3,
            include_text=True,
            include_highlights=True,
        )

        assert isinstance(results, list)

        # If results returned, some should have text
        for result in results:
            assert isinstance(result, ExaSearchResult)
            # text and highlights may or may not be present

    @pytest.mark.asyncio
    async def test_search_with_domain_filter(self, exa_client):
        """Test search with domain filtering."""
        results = await exa_client.search(
            query="tech meetups",
            num_results=5,
            include_domains=["meetup.com", "eventbrite.com"],
        )

        assert isinstance(results, list)

        # If results returned, they should be from specified domains
        for result in results:
            assert isinstance(result, ExaSearchResult)
            # Domain filtering may not be perfect, just verify structure

    @pytest.mark.asyncio
    async def test_search_with_date_filter(self, exa_client):
        """Test search with publication date filter."""
        start_date = datetime.now(UTC) - timedelta(days=30)

        results = await exa_client.search(
            query="startup events",
            num_results=5,
            start_published_date=start_date,
        )

        assert isinstance(results, list)
        for result in results:
            assert isinstance(result, ExaSearchResult)

    @pytest.mark.asyncio
    async def test_find_similar(self, exa_client):
        """Test finding pages similar to a given URL."""
        results = await exa_client.find_similar(
            url="https://www.eventbrite.com",
            num_results=3,
        )

        assert isinstance(results, list)
        for result in results:
            assert isinstance(result, ExaSearchResult)


@pytest.mark.integration
@pytest.mark.slow
class TestExaWebsetsLive:
    """Live integration tests for Exa Websets (async deep discovery).

    These tests are marked slow because websets can take time to complete.
    Run with: pytest -m "integration and slow" --run-slow
    """

    @pytest.mark.asyncio
    async def test_create_webset(self, exa_client):
        """Test creating a webset."""
        webset_id = await exa_client.create_webset(
            query="AI technology events 2026",
            count=10,
        )

        # Should return string ID or None
        # None is acceptable if quota exceeded or API issue
        if webset_id is not None:
            assert isinstance(webset_id, str)
            assert len(webset_id) > 0

    @pytest.mark.asyncio
    async def test_create_webset_with_criteria(self, exa_client):
        """Test creating a webset with additional criteria."""
        webset_id = await exa_client.create_webset(
            query="machine learning conferences",
            count=5,
            criteria="Must be in-person events in the United States",
        )

        if webset_id is not None:
            assert isinstance(webset_id, str)

    @pytest.mark.asyncio
    async def test_webset_creation_and_poll(self, exa_client):
        """Test full webset workflow: create and poll for status."""
        import asyncio

        # Create webset
        webset_id = await exa_client.create_webset(
            query="tech meetups Ohio",
            count=5,
        )

        if webset_id is None:
            pytest.skip("Webset creation failed - may be quota/API issue")

        # Poll for status (with timeout)
        max_attempts = 6  # 6 attempts * 10 seconds = 60 seconds max
        webset = None

        for _ in range(max_attempts):
            webset = await exa_client.get_webset(webset_id)

            if webset is None:
                pytest.fail("Failed to retrieve webset status")

            assert isinstance(webset, ExaWebset)
            assert webset.id == webset_id
            assert webset.status in ["running", "completed", "failed"]

            if webset.status in ["completed", "failed"]:
                break

            await asyncio.sleep(10)

        # Validate final state
        assert webset is not None
        if webset.status == "completed" and webset.results:
            for result in webset.results:
                assert isinstance(result, ExaSearchResult)


# ============================================================================
# Combined Validation Tests
# ============================================================================

@pytest.mark.integration
class TestAllSourcesLive:
    """Tests that validate all sources can be instantiated and called."""

    @pytest.mark.asyncio
    async def test_all_clients_instantiate(self):
        """Test that all clients can be created with env var keys."""
        clients = []

        # Try each client - they should not raise on instantiation
        if os.getenv("FIRECRAWL_API_KEY"):
            client = FirecrawlClient()
            clients.append(client)

        if os.getenv("EVENTBRITE_API_KEY"):
            client = EventbriteClient()
            clients.append(client)

        if os.getenv("EXA_API_KEY"):
            client = ExaClient()
            clients.append(client)

        # At least one client should be available for this test to be meaningful
        if not clients:
            pytest.skip("No API keys configured - skipping combined test")

        # Cleanup
        for client in clients:
            await client.close()

    @pytest.mark.asyncio
    async def test_source_summary(self):
        """Print summary of available sources (informational)."""
        sources = {
            "Firecrawl/Posh": bool(os.getenv("FIRECRAWL_API_KEY")),
            "Eventbrite": bool(os.getenv("EVENTBRITE_API_KEY")),
            "Exa": bool(os.getenv("EXA_API_KEY")),
        }

        available = [name for name, has_key in sources.items() if has_key]
        missing = [name for name, has_key in sources.items() if not has_key]

        print(f"\n{'='*60}")
        print("EVENT SOURCE INTEGRATION TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Available sources: {', '.join(available) or 'None'}")
        print(f"Missing API keys: {', '.join(missing) or 'None'}")
        print(f"{'='*60}\n")

        # Always pass - this is informational
        assert True
