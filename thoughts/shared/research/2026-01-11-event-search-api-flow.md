---
date: 2026-01-11T13:10:20-0500
researcher: Claude (Mayor)
git_commit: 78cd6a35f1502cba6be3108ddeb8680c4ee0f057
branch: main
repository: calendar-club-prototype
topic: "Event Search API Flow - Eventbrite and Exa Integration"
tags: [research, codebase, eventbrite, exa, search, api]
status: complete
last_updated: 2026-01-11
last_updated_by: Claude (Mayor)
---

# Research: Event Search API Flow - Eventbrite and Exa Integration

**Date**: 2026-01-11T13:10:20-0500
**Researcher**: Claude (Mayor)
**Git Commit**: 78cd6a35f1502cba6be3108ddeb8680c4ee0f057
**Branch**: main
**Repository**: calendar-club-prototype

## Research Question

Analysis of the event search API flow based on logs showing:
- Eventbrite destination API returning 404/405 errors
- Exa search succeeding (1 event returned)
- Exa websets endpoint returning 404

## Summary

The event search system uses a multi-source parallel architecture that queries Eventbrite and Exa APIs simultaneously, merges results, and deduplicates them. The logs show expected behavior: Eventbrite's internal API endpoints are unreliable (returning 404/405), causing graceful fallback to empty results, while Exa's search endpoint works but websets (async deep discovery) fail due to a 404 on the `/websets` endpoint.

## Detailed Findings

### 1. Search Flow Architecture

The search flow is orchestrated by `api/agents/search.py:302` via `search_events()`:

1. **ClarifyingAgent** (`api/agents/clarifying.py`) processes user message and extracts `SearchProfile`
2. **Handoff** occurs at `api/index.py:166` when `ready_to_search=True` and `search_profile` is populated
3. **Parallel API calls** via `asyncio.gather()` at `search.py:353`:
   - `_fetch_eventbrite_events()` at line 344
   - `_fetch_exa_events()` at line 348
4. **Results merged** and deduplicated at `search.py:383`
5. **Background Websets** initiated at `index.py:200` for async deep discovery

### 2. Eventbrite Service Implementation

**Location**: `api/services/eventbrite.py`

The Eventbrite service uses internal web APIs since the official Event Search API was deprecated in 2020.

**API Strategy (lines 145-234)**:
- Primary endpoint: `GET /destination/events/{location_slug}/` (line 199)
- Fallback endpoint: `GET /destination/search/?q={location}` (line 209)
- Uses browser User-Agent headers to access internal APIs (line 79)

**Error Handling**:
- 404 on primary → tries fallback endpoint (line 206)
- 404/405 on fallback → logs warning, returns empty list (lines 213-217)
- All `httpx.HTTPError` caught at line 232, returns empty list

**From the logs**:
```
HTTP Request: GET .../destination/events/Columbus%2C%20OH/... "HTTP/1.1 404 NOT FOUND"
Destination API 404, trying search endpoint
HTTP Request: GET .../destination/search/... "HTTP/1.1 405 METHOD NOT ALLOWED"
Destination API returned no events, search unavailable
```

This shows the two-tier fallback working as designed - both endpoints failed, so empty list returned.

### 3. Exa Client Implementation

**Location**: `api/services/exa_client.py`

**Search Endpoint** (lines 68-137):
- `POST https://api.exa.ai/search` (line 123)
- Works correctly per logs: "exa returned 1 events"

**Websets Endpoint** (lines 185-227):
- `POST https://api.exa.ai/websets` (line 219)
- Intended for async deep discovery
- Currently returning 404 per logs

**From the logs**:
```
HTTP Request: POST https://api.exa.ai/search "HTTP/1.1 200 OK"
INFO:api.agents.search:exa returned 1 events
HTTP Request: POST https://api.exa.ai/websets "HTTP/1.1 404 Not Found"
WARNING:api.services.exa_client:Exa create webset error: Client error '404 Not Found'
```

**Error Handling**:
- Webset creation failure returns `None` (line 227)
- Background task logs warning at `background_tasks.py:77`

### 4. Background Websets Flow

**Location**: `api/services/background_tasks.py`

The websets feature starts after returning initial results:

1. `index.py:200` calls `bg_manager.start_webset_discovery()`
2. `background_tasks.py:70` calls `client.create_webset()`
3. On success, `_poll_webset()` task polls status every 5 seconds
4. On completion, pushes `more_events` SSE to frontend

Currently failing because `/websets` endpoint returns 404.

### 5. Multi-Source Result Merging

**Location**: `api/agents/search.py:360-399`

Results from all sources are:
1. Extended into `all_events` list (line 360)
2. Tracked in `sources_used` list (line 361)
3. Deduplicated via URL and title normalization (line 383)
4. Sorted by date (line 392)
5. Limited to 15 events (line 393)

**Deduplication** (`search.py:214-258`):
- URLs normalized: remove `www.`, strip trailing slashes
- Titles normalized: lowercase, remove punctuation, collapse whitespace

## Code References

### Core Files
- `api/agents/search.py:302` - Main search orchestrator
- `api/agents/search.py:71` - `_fetch_eventbrite_events()`
- `api/agents/search.py:131` - `_fetch_exa_events()`
- `api/services/eventbrite.py:96` - `EventbriteClient.search_events()`
- `api/services/eventbrite.py:145` - `_search_via_destination_api()`
- `api/services/exa_client.py:68` - `ExaClient.search()`
- `api/services/exa_client.py:185` - `ExaClient.create_webset()`
- `api/services/background_tasks.py:41` - `start_webset_discovery()`
- `api/index.py:166` - Search handoff from ClarifyingAgent

### Data Models
- `api/models/search.py:30-45` - `SearchProfile`
- `api/models/search.py:48-62` - `EventResult`
- `api/services/eventbrite.py:29-44` - `EventbriteEvent`
- `api/services/exa_client.py:20-32` - `ExaSearchResult`

### Configuration
- `api/config.py` - API keys via `settings.eventbrite_api_key`, `settings.exa_api_key`

## Architecture Documentation

### Error Handling Pattern

All API integrations follow the same pattern:
1. Catch `httpx.HTTPError` at outermost level
2. Log warning with exception details
3. Return empty list (or `None` for websets)
4. Never propagate exceptions to caller

This enables graceful degradation - if one source fails, others continue.

### Singleton Pattern

All service clients use singleton factories:
- `get_eventbrite_client()` at `eventbrite.py:392`
- `get_exa_client()` at `exa_client.py:300`
- `get_event_cache()` at `event_cache.py:415`

### SSE Event Types

The streaming endpoint emits these event types:
- `content` - Message text chunks
- `quick_picks` - Suggested options
- `searching` - Search started indicator
- `events` - Initial event results
- `background_search` - Deep search started
- `more_events` - Webset results (async)
- `done` - Stream complete
- `error` - Error occurred

## Related Research

- `throughts/research/2026-01-10-exa-websets-event-search-research.md` - Exa websets research
- `throughts/plans/2026-01-11-exa-websets-integration.md` - Websets integration planning
- `throughts/shared/plans/2026-01-11-event-source-registry-pattern.md` - Event source architecture

## Open Questions

1. **Eventbrite API availability**: The internal destination API returns 404/405 - has Eventbrite changed their internal API structure?
2. **Exa websets endpoint**: The `/websets` endpoint returns 404 - is this feature still available in the Exa API, or has it been deprecated/moved?
3. **Location hardcoding**: Both Eventbrite and Exa fetchers hardcode "Columbus, OH" - is this intentional for the prototype phase?
