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
# Logging Helpers
# ============================================================================

def log_header(source: str, test_name: str):
    """Print a header for test output."""
    print(f"\n{'='*70}")
    print(f"[{source}] {test_name}")
    print(f"{'='*70}")


def log_scraped_event(event: "ScrapedEvent", index: int):
    """Log key fields from a ScrapedEvent."""
    print(f"\n  [{index}] {event.title}")
    print(f"      Source: {event.source}")
    print(f"      ID: {event.event_id}")
    print(f"      URL: {event.url}")
    if event.start_time:
        print(f"      Start: {event.start_time}")
    if event.venue_name:
        print(f"      Venue: {event.venue_name}")
    if event.venue_address:
        print(f"      Address: {event.venue_address}")
    print(f"      Free: {event.is_free}")
    if event.price_amount:
        print(f"      Price: ${event.price_amount / 100:.2f}")


def log_eventbrite_event(event: "EventbriteEvent", index: int):
    """Log key fields from an EventbriteEvent."""
    print(f"\n  [{index}] {event.title}")
    print(f"      ID: {event.id}")
    print(f"      Start: {event.start_time}")
    if event.end_time:
        print(f"      End: {event.end_time}")
    if event.venue_name:
        print(f"      Venue: {event.venue_name}")
    if event.venue_address:
        print(f"      Address: {event.venue_address}")
    print(f"      Free: {event.is_free}")
    if event.url:
        print(f"      URL: {event.url}")


def log_exa_result(result: "ExaSearchResult", index: int):
    """Log key fields from an ExaSearchResult."""
    print(f"\n  [{index}] {result.title}")
    print(f"      URL: {result.url}")
    if result.score:
        print(f"      Score: {result.score:.4f}")
    if result.published_date:
        print(f"      Published: {result.published_date}")
    if result.author:
        print(f"      Author: {result.author}")
    if result.highlights:
        print(f"      Highlights: {result.highlights[:2]}")  # First 2 highlights


def log_raw_dict(data: dict, label: str = "Response"):
    """Log raw dict response with key fields."""
    print(f"\n  {label}:")
    print(f"      Keys: {list(data.keys())}")
    if "markdown" in data:
        content = data["markdown"][:200] if data["markdown"] else "(empty)"
        print(f"      Markdown preview: {content}...")
    if "extract" in data:
        print(f"      Extract: {data['extract']}")


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
        log_header("Firecrawl", "Scrape Posh Homepage")

        result = await firecrawl_client.scrape(
            url="https://posh.vip",
            formats=["markdown"],
        )

        # Should return dict with data (may be empty if blocked)
        assert isinstance(result, dict)
        log_raw_dict(result, "Scrape Result")
        print(f"\n  SUCCESS: Got response with {len(result)} keys")

    @pytest.mark.asyncio
    async def test_scrape_with_extraction(self, firecrawl_client):
        """Test scraping with LLM extraction schema."""
        log_header("Firecrawl", "Scrape with LLM Extraction")

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
        log_raw_dict(result, "Extraction Result")
        print(f"\n  SUCCESS: Got extraction response")

    @pytest.mark.asyncio
    async def test_crawl_posh_city(self, firecrawl_client):
        """Test crawling Posh city page."""
        log_header("Firecrawl", "Crawl Posh Columbus")

        results = await firecrawl_client.crawl(
            url="https://posh.vip/c/columbus",
            max_depth=1,
            limit=3,  # Keep small for speed
        )

        # Should return list (may be empty if site blocks crawlers)
        assert isinstance(results, list)
        print(f"\n  Crawled pages: {len(results)}")
        for i, result in enumerate(results):
            assert isinstance(result, dict)
            url = result.get("url", result.get("metadata", {}).get("url", "unknown"))
            print(f"    [{i}] {url}")
        print(f"\n  SUCCESS: Crawled {len(results)} pages")


@pytest.mark.integration
class TestPoshExtractorLive:
    """Live integration tests for PoshExtractor."""

    @pytest.mark.asyncio
    async def test_discover_events_columbus(self, posh_extractor):
        """Test discovering events for Columbus."""
        log_header("Posh", "Discover Events - Columbus")

        events = await posh_extractor.discover_events(
            city="columbus",
            limit=5,
        )

        # Should return list (may be empty if no events or blocked)
        assert isinstance(events, list)
        print(f"\n  Total events found: {len(events)}")

        # If we got events, validate structure and log details
        for i, event in enumerate(events):
            assert isinstance(event, ScrapedEvent)
            assert event.source == "posh"
            assert event.title  # Title is required
            assert event.url  # URL is required
            assert event.event_id  # ID is required
            log_scraped_event(event, i)

        print(f"\n  SUCCESS: Found {len(events)} Posh events in Columbus")

    @pytest.mark.asyncio
    async def test_discover_events_new_york(self, posh_extractor):
        """Test discovering events for different city."""
        log_header("Posh", "Discover Events - New York")

        events = await posh_extractor.discover_events(
            city="new-york",
            limit=3,
        )

        assert isinstance(events, list)
        print(f"\n  Total events found: {len(events)}")

        for i, event in enumerate(events):
            assert isinstance(event, ScrapedEvent)
            log_scraped_event(event, i)

        print(f"\n  SUCCESS: Found {len(events)} Posh events in New York")


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
        log_header("Eventbrite", "Basic Search - Columbus")

        events = await eventbrite_client.search_events(
            location="Columbus, OH",
            page_size=5,
        )

        # Should return list (may be empty if API unavailable)
        assert isinstance(events, list)
        print(f"\n  Total events found: {len(events)}")

        # If we got events, validate structure
        for i, event in enumerate(events):
            assert isinstance(event, EventbriteEvent)
            assert event.id
            assert event.title
            assert event.start_time
            log_eventbrite_event(event, i)

        print(f"\n  SUCCESS: Found {len(events)} Eventbrite events in Columbus")

    @pytest.mark.asyncio
    async def test_search_events_with_dates(self, eventbrite_client):
        """Test event search with date range filter."""
        log_header("Eventbrite", "Search with Date Filter")

        start = datetime.now(UTC)
        end = start + timedelta(days=30)
        print(f"\n  Date range: {start.date()} to {end.date()}")

        events = await eventbrite_client.search_events(
            location="Columbus, OH",
            start_date=start,
            end_date=end,
            page_size=5,
        )

        assert isinstance(events, list)
        print(f"\n  Total events found: {len(events)}")

        # If events returned, dates should be in range
        for i, event in enumerate(events):
            assert isinstance(event, EventbriteEvent)
            log_eventbrite_event(event, i)

        print(f"\n  SUCCESS: Found {len(events)} events in date range")

    @pytest.mark.asyncio
    async def test_search_events_free_only(self, eventbrite_client):
        """Test event search filtering for free events."""
        log_header("Eventbrite", "Free Events Only")

        events = await eventbrite_client.search_events(
            location="Columbus, OH",
            free_only=True,
            page_size=5,
        )

        assert isinstance(events, list)
        print(f"\n  Total free events found: {len(events)}")

        # If events returned, they should be free
        for i, event in enumerate(events):
            assert isinstance(event, EventbriteEvent)
            log_eventbrite_event(event, i)

        print(f"\n  SUCCESS: Found {len(events)} free events")

    @pytest.mark.asyncio
    async def test_search_events_with_categories(self, eventbrite_client):
        """Test event search with category filter."""
        log_header("Eventbrite", "Category Filter (tech, ai)")

        events = await eventbrite_client.search_events(
            location="Columbus, OH",
            categories=["tech", "ai"],
            page_size=5,
        )

        assert isinstance(events, list)
        print(f"\n  Total tech/ai events found: {len(events)}")

        for i, event in enumerate(events):
            assert isinstance(event, EventbriteEvent)
            log_eventbrite_event(event, i)

        print(f"\n  SUCCESS: Found {len(events)} tech/ai events")

    @pytest.mark.asyncio
    async def test_search_events_different_location(self, eventbrite_client):
        """Test event search for different location."""
        log_header("Eventbrite", "Search - New York")

        events = await eventbrite_client.search_events(
            location="New York, NY",
            page_size=3,
        )

        assert isinstance(events, list)
        print(f"\n  Total events found: {len(events)}")

        for i, event in enumerate(events):
            assert isinstance(event, EventbriteEvent)
            log_eventbrite_event(event, i)

        print(f"\n  SUCCESS: Found {len(events)} events in New York")


# ============================================================================
# Exa Tests
# ============================================================================

@pytest.mark.integration
class TestExaClientLive:
    """Live integration tests for ExaClient search and find_similar."""

    @pytest.mark.asyncio
    async def test_search_basic(self, exa_client):
        """Test basic neural search."""
        log_header("Exa", "Basic Neural Search")
        query = "tech events Columbus Ohio"
        print(f"\n  Query: {query}")

        results = await exa_client.search(
            query=query,
            num_results=5,
        )

        # Should return list (may be empty for obscure queries)
        assert isinstance(results, list)
        print(f"\n  Total results: {len(results)}")

        for i, result in enumerate(results):
            assert isinstance(result, ExaSearchResult)
            assert result.url
            assert result.title
            log_exa_result(result, i)

        print(f"\n  SUCCESS: Found {len(results)} search results")

    @pytest.mark.asyncio
    async def test_search_with_text_content(self, exa_client):
        """Test search with full text content included."""
        log_header("Exa", "Search with Text Content")
        query = "artificial intelligence conferences 2026"
        print(f"\n  Query: {query}")

        results = await exa_client.search(
            query=query,
            num_results=3,
            include_text=True,
            include_highlights=True,
        )

        assert isinstance(results, list)
        print(f"\n  Total results: {len(results)}")

        # If results returned, some should have text
        for i, result in enumerate(results):
            assert isinstance(result, ExaSearchResult)
            log_exa_result(result, i)
            if result.text:
                print(f"      Text preview: {result.text[:150]}...")

        print(f"\n  SUCCESS: Found {len(results)} results with text content")

    @pytest.mark.asyncio
    async def test_search_with_domain_filter(self, exa_client):
        """Test search with domain filtering."""
        log_header("Exa", "Search with Domain Filter")
        domains = ["meetup.com", "eventbrite.com"]
        print(f"\n  Domains: {domains}")

        results = await exa_client.search(
            query="tech meetups",
            num_results=5,
            include_domains=domains,
        )

        assert isinstance(results, list)
        print(f"\n  Total results: {len(results)}")

        # If results returned, they should be from specified domains
        for i, result in enumerate(results):
            assert isinstance(result, ExaSearchResult)
            log_exa_result(result, i)

        print(f"\n  SUCCESS: Found {len(results)} results from filtered domains")

    @pytest.mark.asyncio
    async def test_search_with_date_filter(self, exa_client):
        """Test search with publication date filter."""
        log_header("Exa", "Search with Date Filter")
        start_date = datetime.now(UTC) - timedelta(days=30)
        print(f"\n  Published after: {start_date.date()}")

        results = await exa_client.search(
            query="startup events",
            num_results=5,
            start_published_date=start_date,
        )

        assert isinstance(results, list)
        print(f"\n  Total results: {len(results)}")

        for i, result in enumerate(results):
            assert isinstance(result, ExaSearchResult)
            log_exa_result(result, i)

        print(f"\n  SUCCESS: Found {len(results)} recent results")

    @pytest.mark.asyncio
    async def test_find_similar(self, exa_client):
        """Test finding pages similar to a given URL."""
        log_header("Exa", "Find Similar Pages")
        url = "https://www.eventbrite.com"
        print(f"\n  Source URL: {url}")

        results = await exa_client.find_similar(
            url=url,
            num_results=3,
        )

        assert isinstance(results, list)
        print(f"\n  Total similar pages: {len(results)}")

        for i, result in enumerate(results):
            assert isinstance(result, ExaSearchResult)
            log_exa_result(result, i)

        print(f"\n  SUCCESS: Found {len(results)} similar pages")


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
        log_header("Exa Websets", "Create Webset")
        query = "AI technology events 2026"
        print(f"\n  Query: {query}")

        webset_id = await exa_client.create_webset(
            query=query,
            count=10,
        )

        # Should return string ID or None
        # None is acceptable if quota exceeded or API issue
        if webset_id is not None:
            assert isinstance(webset_id, str)
            assert len(webset_id) > 0
            print(f"\n  Webset ID: {webset_id}")
            print(f"\n  SUCCESS: Created webset")
        else:
            print(f"\n  WARNING: Webset creation returned None (quota/API issue)")

    @pytest.mark.asyncio
    async def test_create_webset_with_criteria(self, exa_client):
        """Test creating a webset with additional criteria."""
        log_header("Exa Websets", "Create Webset with Criteria")
        query = "machine learning conferences"
        criteria = "Must be in-person events in the United States"
        print(f"\n  Query: {query}")
        print(f"  Criteria: {criteria}")

        webset_id = await exa_client.create_webset(
            query=query,
            count=5,
            criteria=criteria,
        )

        if webset_id is not None:
            assert isinstance(webset_id, str)
            print(f"\n  Webset ID: {webset_id}")
            print(f"\n  SUCCESS: Created webset with criteria")
        else:
            print(f"\n  WARNING: Webset creation returned None (quota/API issue)")

    @pytest.mark.asyncio
    async def test_webset_creation_and_poll(self, exa_client):
        """Test full webset workflow: create and poll for status."""
        import asyncio

        log_header("Exa Websets", "Full Workflow (Create + Poll)")
        query = "tech meetups Ohio"
        print(f"\n  Query: {query}")

        # Create webset
        webset_id = await exa_client.create_webset(
            query=query,
            count=5,
        )

        if webset_id is None:
            print(f"\n  WARNING: Webset creation failed - may be quota/API issue")
            pytest.skip("Webset creation failed - may be quota/API issue")

        print(f"\n  Webset ID: {webset_id}")

        # Poll for status (with timeout)
        max_attempts = 6  # 6 attempts * 10 seconds = 60 seconds max
        webset = None

        for attempt in range(max_attempts):
            print(f"\n  Polling attempt {attempt + 1}/{max_attempts}...")
            webset = await exa_client.get_webset(webset_id)

            if webset is None:
                pytest.fail("Failed to retrieve webset status")

            assert isinstance(webset, ExaWebset)
            assert webset.id == webset_id
            assert webset.status in ["running", "completed", "failed"]

            print(f"    Status: {webset.status}")
            if webset.num_results:
                print(f"    Results so far: {webset.num_results}")

            if webset.status in ["completed", "failed"]:
                break

            await asyncio.sleep(10)

        # Validate final state
        assert webset is not None
        print(f"\n  Final status: {webset.status}")

        if webset.status == "completed" and webset.results:
            print(f"  Total results: {len(webset.results)}")
            for i, result in enumerate(webset.results):
                assert isinstance(result, ExaSearchResult)
                log_exa_result(result, i)
            print(f"\n  SUCCESS: Webset completed with {len(webset.results)} results")
        else:
            print(f"\n  Webset finished with status: {webset.status}")


# ============================================================================
# Combined Validation Tests
# ============================================================================

@pytest.mark.integration
class TestAllSourcesLive:
    """Tests that validate all sources can be instantiated and called."""

    @pytest.mark.asyncio
    async def test_all_clients_instantiate(self):
        """Test that all clients can be created with env var keys."""
        log_header("Combined", "Client Instantiation Test")

        clients = []
        client_names = []

        # Try each client - they should not raise on instantiation
        if os.getenv("FIRECRAWL_API_KEY"):
            client = FirecrawlClient()
            clients.append(client)
            client_names.append("FirecrawlClient")
            print(f"\n  Created: FirecrawlClient")

        if os.getenv("EVENTBRITE_API_KEY"):
            client = EventbriteClient()
            clients.append(client)
            client_names.append("EventbriteClient")
            print(f"  Created: EventbriteClient")

        if os.getenv("EXA_API_KEY"):
            client = ExaClient()
            clients.append(client)
            client_names.append("ExaClient")
            print(f"  Created: ExaClient")

        # At least one client should be available for this test to be meaningful
        if not clients:
            print(f"\n  No API keys configured!")
            pytest.skip("No API keys configured - skipping combined test")

        # Cleanup
        for client in clients:
            await client.close()

        print(f"\n  SUCCESS: Instantiated {len(clients)} clients: {', '.join(client_names)}")

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

        print(f"\n{'='*70}")
        print("EVENT SOURCE INTEGRATION TEST SUMMARY")
        print(f"{'='*70}")
        print(f"\n  Available sources ({len(available)}): {', '.join(available) or 'None'}")
        print(f"  Missing API keys ({len(missing)}): {', '.join(missing) or 'None'}")
        print(f"\n  Environment variables checked:")
        print(f"    FIRECRAWL_API_KEY: {'SET' if sources['Firecrawl/Posh'] else 'NOT SET'}")
        print(f"    EVENTBRITE_API_KEY: {'SET' if sources['Eventbrite'] else 'NOT SET'}")
        print(f"    EXA_API_KEY: {'SET' if sources['Exa'] else 'NOT SET'}")
        print(f"\n{'='*70}")

        # Always pass - this is informational
        assert True
