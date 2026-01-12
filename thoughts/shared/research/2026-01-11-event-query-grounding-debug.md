---
date: 2026-01-11T12:00:00-05:00
researcher: Claude
git_commit: 936886e69700bb81dc760f3eaa0efc28c5ab6416
branch: main
repository: calendar-club-prototype
topic: "Debug: Events not grounded to correct location/dates"
tags: [research, codebase, debugging, exa, firecrawl, eventbrite, meetup, query-construction, logging]
status: complete
last_updated: 2026-01-11
last_updated_by: Claude
---

# Research: Event Query Grounding Debug

**Date**: 2026-01-11T12:00:00-05:00
**Researcher**: Claude
**Git Commit**: 936886e69700bb81dc760f3eaa0efc28c5ab6416
**Branch**: main
**Repository**: calendar-club-prototype

## Research Question

Events being shown aren't grounded - they're not actually in Columbus, Ohio or happening at the requested time (e.g., "next week"). Need to:
1. Understand how queries are constructed for each external service
2. Identify what logging exists for outbound queries
3. Document the root cause of the grounding failure

## Summary

The grounding issues stem from **multiple architectural problems**:

1. **Exa's date filter misuse**: The `start_published_date` parameter filters by when a *webpage was published*, NOT when an *event occurs*
2. **Truncated query logging**: All services only log first 50 characters of queries (`query[:50]`)
3. **No complete request payload logging**: No service logs the full API request being sent
4. **Posh/Firecrawl has no query logging at all** in the adapter
5. **No grounding validation**: Events are never validated against requested time/location after fetching

## Detailed Findings

### Exa Query Construction (`exa_client.py:353-405`)

**How queries are built:**
```python
query_parts = ["events", "Columbus Ohio"]

if hasattr(profile, "categories") and profile.categories:
    query_parts.extend(profile.categories)

if hasattr(profile, "keywords") and profile.keywords:
    query_parts.extend(profile.keywords)

# Add time context - ONLY month/year, not specific dates
if hasattr(profile, "time_window") and profile.time_window:
    if profile.time_window.start:
        query_parts.append(profile.time_window.start.strftime("%B %Y"))  # e.g., "January 2026"

query = " ".join(query_parts)
```

**Root Cause Issue #1**: The `start_published_date` and `end_published_date` parameters sent to Exa filter by **page publication date**, NOT event date:
```python
return await client.search(
    query=query,
    start_published_date=start_date,  # This is WRONG for event filtering!
    end_published_date=end_date,       # This is WRONG for event filtering!
    include_domains=include_domains,
)
```

**Current logging** (`exa_client.py:124-128`):
```python
logger.debug(
    "🌐 [Exa] Starting search | query=%s num_results=%d",
    query[:50],  # TRUNCATED - only first 50 chars shown!
    num_results,
)
```

**Missing from logs**:
- Full query string
- Date range filters (`startPublishedDate`, `endPublishedDate`)
- Include/exclude domains list
- Complete payload being sent to API

---

### Firecrawl/Posh Query Construction (`firecrawl.py:370-406`)

**How queries are built:**
```python
city = "columbus"  # Hardcoded - no logging of this!

events = await extractor.discover_events(city=city, limit=30)

# Post-fetch filtering (no logging of what's filtered)
for event in events:
    if profile.time_window.start and event.start_time:
        if event.start_time < profile.time_window.start:
            continue  # Silently skipped
```

**Root Cause Issue #2**: **No logging whatsoever** in the `search_events_adapter` function. The only logging is at the `discover_events` level:
```python
logger.info("Discovered %d Posh events for %s", len(events), city)
```

**Missing from logs**:
- City being queried
- Time window being used for filtering
- How many events were filtered out
- Which events failed grounding checks

---

### Eventbrite Query Construction (`eventbrite.py:428-469`)

**How queries are built:**
```python
location = "Columbus, OH"  # Hardcoded
categories = profile.categories if hasattr(profile, "categories") else None
free_only = profile.free_only if hasattr(profile, "free_only") else False

# Date extraction
start_date, end_date = # extracted from profile.time_window
```

**Current logging** (`eventbrite.py:201-205`):
```python
logger.debug(
    "🌐 [Eventbrite] Starting search | endpoint=%s location=%s",
    endpoint,
    location or "Columbus--OH",
)
```

**Missing from logs**:
- Categories being filtered
- Free only flag
- Start/end date parameters
- Full `params` dict being sent

---

### Meetup Query Construction (`meetup.py:298-363`)

**How queries are built:**
```python
query_parts = []
if hasattr(profile, "categories") and profile.categories:
    query_parts.extend(profile.categories)
if hasattr(profile, "keywords") and profile.keywords:
    query_parts.extend(profile.keywords)

query = " ".join(query_parts) if query_parts else "events"

# Location is hardcoded
latitude=39.9612,  # Columbus, OH
longitude=-82.9988,
```

**Current logging** (`meetup.py:333-338`):
```python
logger.debug(
    "🌐 [Meetup] Starting search | query=%s start=%s end=%s",
    query[:50],  # TRUNCATED
    start_date,
    end_date,
)
```

**Missing from logs**:
- Full query string
- Latitude/longitude being used
- Radius parameter

---

### Search Agent Result Handling (`search.py:97-125`)

**Additional Issue - Exa Result Conversion**:
```python
def _convert_exa_result(result: ExaSearchResult) -> EventResult:
    # Extract date from result if available
    date_str = datetime.now().isoformat()  # DEFAULT: Uses NOW, not event date!
    if result.published_date:
        date_str = result.published_date.isoformat()  # Uses PAGE publication date!

    return EventResult(
        location="Columbus, OH",  # HARDCODED - not from Exa result!
        # ...
    )
```

**Root Cause Issue #3**: Exa results have their `published_date` (page publication) used as the event date, which is fundamentally wrong.

---

## Root Cause Summary

| Service | Location Issue | Date Issue | Logging Gap |
|---------|----------------|------------|-------------|
| **Exa** | Hardcoded in query string | Uses `publishedDate` (page date, not event date) | Query truncated to 50 chars, no payload logged |
| **Posh** | Hardcoded "columbus" | Post-fetch filtering only | No adapter logging at all |
| **Eventbrite** | Hardcoded "Columbus, OH" | Correct date filtering | No params logged |
| **Meetup** | Hardcoded lat/lon | Correct date filtering | Query truncated, no lat/lon logged |

## Code References

- `api/services/exa_client.py:353-405` - Exa adapter query construction
- `api/services/exa_client.py:124-128` - Exa truncated logging
- `api/services/firecrawl.py:370-406` - Posh adapter (no logging)
- `api/services/eventbrite.py:201-205` - Eventbrite logging (no params)
- `api/services/meetup.py:333-338` - Meetup truncated logging
- `api/agents/search.py:97-125` - Exa result conversion (wrong date handling)

## What Complete Logging Should Look Like

Each service adapter should log the **complete outbound request** with an emoji prefix for easy scanning:

```python
logger.debug(
    "📤 [Exa] Outbound Query | query='%s' "
    "start_published=%s end_published=%s "
    "include_domains=%s num_results=%d",
    query,  # FULL query, not truncated
    start_published_date,
    end_published_date,
    include_domains,
    num_results,
)
```

## Architecture Documentation

The current query flow:

```
User Message
    ↓
ClarifyingAgent (builds SearchProfile)
    ↓
SearchProfile {time_window, categories, keywords, free_only}
    ↓
search_events() dispatches to all enabled sources
    ↓
┌─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│ Exa Adapter     │ Posh Adapter    │ Eventbrite      │ Meetup Adapter  │
│ (query string)  │ (city slug)     │ (location slug) │ (GraphQL vars)  │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
    ↓                   ↓                   ↓                   ↓
┌─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│ Exa API         │ Firecrawl API   │ Eventbrite API  │ Meetup GraphQL  │
│ /search         │ /scrape         │ /destination    │ /gql            │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
```

## Open Questions

1. Should Exa be filtered out as an event source since it can't reliably provide event dates?
2. Should we add a validation layer that checks returned events against the requested time window?
3. Should location be extracted from SearchProfile instead of hardcoded?
