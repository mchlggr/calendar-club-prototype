---
date: 2026-01-11T17:18:40Z
researcher: Claude (Opus 4.5)
git_commit: 78cd6a35f1502cba6be3108ddeb8680c4ee0f057
branch: main
repository: mchlggr/calendar-club-prototype
topic: "Meetup GraphQL API Integration & Event Source Modularity"
tags: [research, meetup, graphql, event-sources, modularity, architecture]
status: complete
last_updated: 2026-01-11
last_updated_by: Claude (Opus 4.5)
---

# Research: Meetup GraphQL API Integration & Event Source Modularity

**Date**: 2026-01-11T17:18:40Z
**Researcher**: Claude (Opus 4.5)
**Git Commit**: 78cd6a35f1502cba6be3108ddeb8680c4ee0f057
**Branch**: main
**Repository**: mchlggr/calendar-club-prototype

## Research Question

How should we integrate the Meetup GraphQL API as an additional event source, what credentials are needed, and how can we improve the modularity of our event source architecture?

## Summary

The codebase has three existing event sources (Eventbrite, EXA, Firecrawl) following a consistent convention-based pattern. Adding Meetup as a fourth source is straightforward using the `gql` Python library for GraphQL. However, **Meetup Pro subscription is required** for API access, which may be a blocker.

The current architecture is well-structured but could benefit from a formal `Protocol` definition to enforce the client contract. The existing pattern is solid; a light-touch formalization would prevent drift as more sources are added.

## Detailed Findings

### 1. Current Event Source Architecture

#### File Structure
```
api/services/
├── eventbrite.py     # EventbriteClient + EventbriteEvent
├── exa_client.py     # ExaClient + ExaSearchResult + ExaWebset
├── firecrawl.py      # FirecrawlClient + PoshExtractor + ScrapedEvent
├── event_cache.py    # EventCache + CachedEvent
└── __init__.py       # Exports all clients and models

api/agents/
└── search.py         # search_events() orchestrator + EventResult
```

#### Client Pattern (All Three Sources)
Each client follows an identical structure:
- **Constructor**: `__init__(api_key: str | None = None)` with env fallback
- **HTTP Client**: Lazy-initialized `httpx.AsyncClient` via `_get_client()`
- **Close**: `async def close()` for cleanup
- **Search Method**: Returns `list[SourceEvent]` (source-specific model)
- **Parser**: Private `_parse_*()` methods for response handling
- **Singleton**: Module-level `_client` variable + `get_*_client()` factory

#### Data Flow
```
SearchProfile → search_events() → parallel fetch per source
                    ↓
    _fetch_eventbrite_events() → EventbriteClient → EventbriteEvent
    _fetch_exa_events()        → ExaClient        → ExaSearchResult
                    ↓
         Convert to EventResult → deduplicate → sort → SearchResult
```

### 2. Meetup GraphQL API Details

#### Endpoint & Authentication
| Item | Value |
|------|-------|
| **GraphQL Endpoint** | `https://api.meetup.com/gql` |
| **Extended Endpoint** | `https://api.meetup.com/gql-ext` |
| **Auth Method** | OAuth 2.0 (Bearer token) |
| **Auth Header** | `Authorization: Bearer {ACCESS_TOKEN}` |
| **Rate Limit** | 500 points per 60 seconds |

#### OAuth 2.0 Flows Supported
- **Server Flow**: For apps with secure secret storage
- **JWT Flow**: For server-to-server (RSA-signed JWT)
- **Refresh Token Flow**: Single-use refresh tokens
- **Implicit Flow**: For browser clients

#### Critical Requirement
**A Meetup Pro subscription is required** to create OAuth consumers. API access approval is not guaranteed.

#### Key Queries for Event Search

**Search by Location** (requires lat/lon - geocoding needed):
```graphql
query SearchEvents($lat: Float!, $lon: Float!, $radius: Float) {
  rankedEvents(filter: {lat: $lat, lon: $lon, radius: $radius}) {
    edges {
      node {
        id
        title
        description
        dateTime
        duration
        eventUrl
        venue {
          name
          address
          lat
          lon
        }
        group {
          name
          urlname
        }
        featuredEventPhoto {
          baseUrl
        }
        eventHosts {
          name
        }
      }
    }
    pageInfo {
      endCursor
      hasNextPage
    }
  }
}
```

#### Available Event Fields
| Field | Type | Notes |
|-------|------|-------|
| `id` | ID | Event identifier |
| `title` | String | Event title |
| `description` | String | HTML (masked for non-members) |
| `dateTime` | String | ISO 8601 format |
| `duration` | Int | Milliseconds (3hr default) |
| `eventUrl` | String | Direct link |
| `venue` | Object | name, address, lat, lon |
| `group` | Object | name, urlname |
| `featuredEventPhoto` | Object | baseUrl for image |

#### Official Documentation
- [API Introduction](https://www.meetup.com/graphql/)
- [API Guide](https://www.meetup.com/api/guide/)
- [Schema Reference](https://www.meetup.com/graphql/schema/)
- [API Playground](https://www.meetup.com/api/playground/)
- [Authentication Guide](https://www.meetup.com/graphql/authentication/)

### 3. Python GraphQL Library Recommendation

#### Comparison

| Feature | gql | sgqlc | python-graphql-client |
|---------|-----|-------|----------------------|
| **Stars** | 1.7k | 547 | N/A |
| **Latest Release** | Nov 2025 (v4.2.0b0) | Active | Mar 2021 (abandoned) |
| **Async Support** | Excellent | Yes | Basic |
| **Maintenance** | Active (61 contributors) | Active (32) | Abandoned |

#### Recommendation: `gql`

**Why gql wins:**
- Most actively maintained (releases through Nov 2025)
- Excellent async support with `AIOHTTPTransport`
- Schema validation from transport
- Reconnecting WebSocket support
- 11,000+ dependent projects

**Installation:**
```bash
pip install gql[aiohttp]
```

**Example Integration:**
```python
from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport

transport = AIOHTTPTransport(
    url="https://api.meetup.com/gql",
    headers={"Authorization": f"Bearer {token}"}
)

client = Client(transport=transport, fetch_schema_from_transport=True)

query = gql("""
    query($lat: Float!, $lon: Float!) {
        rankedEvents(filter: {lat: $lat, lon: $lon}) {
            edges { node { id title dateTime } }
        }
    }
""")

async with client as session:
    result = await session.execute(query, variable_values={"lat": 39.96, "lon": -83.00})
```

### 4. Modularity Assessment

#### What's Working Well

1. **Consistent Client Structure**: All three clients follow the same pattern (constructor, lazy client, close, search, parse, singleton)

2. **Parallel Execution**: `asyncio.gather()` with `return_exceptions=True` provides graceful degradation

3. **Clean Separation**: Each source in its own file with its own Pydantic model

4. **Unified Output**: `EventResult` as the common API response format

5. **Source Attribution**: `SearchResult.source` tracks which APIs contributed

#### Areas for Improvement

1. **No Formal Contract**: Clients follow convention but there's no enforced interface. A new contributor could accidentally break the pattern.

2. **Hardcoded Source List**: `search_events()` has if-statements for each source rather than iterating over registered sources.

3. **Duplicate Conversion Logic**: Each `_fetch_*_events()` function repeats similar conversion patterns.

### 5. Proposed Architecture Improvements

#### Option A: Add Protocol Definition (Recommended - Light Touch)

Create a Protocol to document and enforce the client contract without requiring inheritance:

```python
# api/services/base.py
from typing import Protocol, TypeVar
from pydantic import BaseModel

E = TypeVar("E", bound=BaseModel, covariant=True)

class EventSourceClient(Protocol[E]):
    """Protocol for event source clients."""

    async def search(
        self,
        location: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        categories: list[str] | None = None,
        limit: int = 10,
    ) -> list[E]:
        """Search for events. Returns source-specific event models."""
        ...

    async def close(self) -> None:
        """Close HTTP client connections."""
        ...
```

**Pros:**
- Documents the expected interface
- Type checkers can validate implementations
- No changes to existing code required
- Duck typing still works

**Cons:**
- Minor addition to codebase
- Doesn't solve registration problem

#### Option B: Registry Pattern (More Comprehensive)

Add a source registry for dynamic source management:

```python
# api/services/registry.py
from dataclasses import dataclass
from typing import Callable, Awaitable

@dataclass
class EventSource:
    name: str
    client_factory: Callable[[], EventSourceClient]
    fetcher: Callable[[SearchProfile], Awaitable[list[EventResult]]]
    config_key: str  # e.g., "meetup_api_key"

_sources: dict[str, EventSource] = {}

def register_source(source: EventSource) -> None:
    _sources[source.name] = source

def get_active_sources(settings) -> list[EventSource]:
    return [s for s in _sources.values() if getattr(settings, s.config_key, None)]
```

Then `search_events()` becomes:
```python
async def search_events(profile: SearchProfile) -> SearchResult:
    settings = get_settings()
    sources = get_active_sources(settings)

    tasks = [s.fetcher(profile) for s in sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # ... merge and deduplicate
```

**Pros:**
- Adding new sources requires no changes to search.py
- Sources are self-registering
- Easier testing (mock registry)

**Cons:**
- More complex
- May be over-engineering for 4-5 sources

#### Recommendation

**Start with Option A (Protocol)**. It formalizes the contract with minimal disruption. If you add 2+ more sources beyond Meetup, consider migrating to Option B.

### 6. Implementation Steps for Meetup Integration

1. **Verify Meetup Pro Access**
   - Confirm you have Meetup Pro subscription
   - Create OAuth consumer at Meetup developer portal
   - Store credentials securely

2. **Add Dependencies**
   ```bash
   pip install gql[aiohttp]
   # Add to requirements.txt/pyproject.toml
   ```

3. **Create Client** (`api/services/meetup.py`)
   - `MeetupClient` class with gql integration
   - `MeetupEvent` Pydantic model
   - `get_meetup_client()` singleton factory

4. **Add Fetcher** in `search.py`
   - `_fetch_meetup_events(profile: SearchProfile) -> list[EventResult]`
   - Handle geocoding (profile.location → lat/lon)

5. **Integrate in Orchestrator**
   - Add `has_meetup = bool(settings.meetup_api_key)` check
   - Add task to parallel fetch if enabled

6. **Configuration**
   - Add `MEETUP_API_KEY` to `.env.example`
   - Add `meetup_api_key` to Settings model
   - Add `MEETUP_CLIENT_ID` and `MEETUP_CLIENT_SECRET` for OAuth

7. **Handle Geocoding**
   - Meetup requires lat/lon, not city names
   - Either use existing geocoding or add dedicated service

## Code References

- `api/services/eventbrite.py:46-62` - Client pattern to follow
- `api/services/exa_client.py:41-48` - Simpler single-client pattern
- `api/services/__init__.py:12-22` - Export pattern
- `api/agents/search.py:302-399` - Orchestrator integration point
- `api/agents/search.py:71-128` - Fetcher function pattern
- `api/config.py` - Settings model for API keys

## Architecture Documentation

### Current Pattern (Convention-Based)
```
                    ┌─────────────────────────────────────┐
                    │         search_events()             │
                    │  (api/agents/search.py:302-399)     │
                    └──────────────┬──────────────────────┘
                                   │
        ┌─────────────┬────────────┴────────────┬─────────────┐
        ▼             ▼                         ▼             ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│ Eventbrite    │ │ EXA           │ │ Firecrawl     │ │ Meetup (new)  │
│ Client        │ │ Client        │ │ + Extractor   │ │ Client        │
└───────┬───────┘ └───────┬───────┘ └───────┬───────┘ └───────┬───────┘
        │                 │                 │                 │
        ▼                 ▼                 ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│EventbriteEvent│ │ExaSearchResult│ │ ScrapedEvent  │ │ MeetupEvent   │
└───────┬───────┘ └───────┬───────┘ └───────┬───────┘ └───────┬───────┘
        │                 │                 │                 │
        └────────────────┬┴─────────────────┴─────────────────┘
                         ▼
               ┌───────────────────┐
               │   EventResult     │
               │ (unified format)  │
               └─────────┬─────────┘
                         ▼
               ┌───────────────────┐
               │  deduplicate()    │
               │  sort() + limit   │
               └─────────┬─────────┘
                         ▼
               ┌───────────────────┐
               │  SearchResult     │
               └───────────────────┘
```

## Related Research

- `throughts/research/2026-01-10-exa-websets-event-search-research.md`
- `throughts/research/2026-01-10-firecrawl-integration-research.md`
- `throughts/research/Key Event API Sources and Their Limits.md`

## Open Questions

1. **Meetup Pro Access**: Do you have a Meetup Pro subscription? This is required for API access.

2. **OAuth Flow Choice**: Which OAuth flow fits best?
   - Server Flow: If you have user login
   - JWT Flow: If server-to-server without user interaction

3. **Geocoding Strategy**: How should we convert city names to lat/lon?
   - Use existing geocoding if available
   - Add new geocoding service (Google Maps, Nominatim, etc.)

4. **Rate Limit Handling**: Should we implement request queuing for the 500 points/60s limit?

## External Sources

- [Meetup GraphQL API](https://www.meetup.com/graphql/)
- [Meetup API Guide](https://www.meetup.com/api/guide/)
- [Meetup API Playground](https://www.meetup.com/api/playground/)
- [gql Python Library](https://github.com/graphql-python/gql)
- [gql Documentation](https://gql.readthedocs.io/)
