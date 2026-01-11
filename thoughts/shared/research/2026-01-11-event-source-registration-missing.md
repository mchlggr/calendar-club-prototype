---
date: 2026-01-11T20:29:17Z
researcher: Claude
git_commit: 91d7b1a71f14dc11ebc4906cba3dfcd614424dfd
branch: main
repository: calendarclub/rig
topic: "Event source registration missing - no web searches executed"
tags: [research, codebase, event-sources, registration, search]
status: complete
last_updated: 2026-01-11
last_updated_by: Claude
---

# Research: Event Source Registration Missing - No Web Searches Executed

**Date**: 2026-01-11T20:29:17Z
**Researcher**: Claude
**Git Commit**: 91d7b1a71f14dc11ebc4906cba3dfcd614424dfd
**Branch**: main
**Repository**: calendarclub/rig

## Research Question

Why are the Eventbrite and Exa web searches not executing despite the code paths existing?

## Summary

**Root Cause**: The event source registration functions `register_eventbrite_source()` and `register_exa_source()` are **defined and exported but never called**. As a result, the global event source registry is empty when `search_events()` attempts to find enabled sources, causing an immediate early return with no external API calls.

## Detailed Findings

### Evidence from Logs

The provided logs show:

```
2026-01-11 15:23:45,165 - api.index - DEBUG - 🔍 [Search] Handoff | categories=['technology'] time_window=start=None end=None keywords=None
2026-01-11 15:23:45,166 - api.index - DEBUG - 📭 [Search] No results | session=4e9a8a77-4795-4544-a62c-9dddcdd1b410
```

**Critical observations:**
1. The `🔍 [Search] Handoff` log (from `api/index.py:188-192`) shows search is being triggered
2. Immediately followed by `📭 [Search] No results` (from `api/index.py:242-244`)
3. **Missing**: `🔍 [Search] Starting parallel fetch` (from `api/agents/search.py:238-240`)
4. **Missing**: `🌐 [Eventbrite] Starting search` (from `api/services/eventbrite.py`)
5. **Missing**: `🌐 [Exa] Starting search` (from `api/services/exa_client.py`)

The absence of the parallel fetch log and any external API logs indicates `search_events()` returned early.

### The Registration System

#### EventSource Registry Pattern (`api/services/base.py`)

The codebase uses a registry pattern for event sources:

```python
# api/services/base.py:126-140
_registry: EventSourceRegistry | None = None

def get_event_source_registry() -> EventSourceRegistry:
    global _registry
    if _registry is None:
        _registry = EventSourceRegistry()
    return _registry
```

Sources must be explicitly registered to be available:

```python
# api/services/base.py:109-111
def get_enabled(self) -> list[EventSource]:
    """Get all enabled sources, sorted by priority."""
    return [s for s in self.get_all() if s.is_enabled()]
```

#### Registration Functions Exist But Are Never Called

**Eventbrite registration** (`api/services/eventbrite.py:472-486`):
```python
def register_eventbrite_source() -> None:
    """Register Eventbrite as an event source in the global registry."""
    from api.services.base import EventSource, register_event_source

    api_key = os.getenv("EVENTBRITE_API_KEY", "")

    source = EventSource(
        name="eventbrite",
        search_fn=search_events_adapter,
        is_enabled_fn=lambda: bool(api_key),
        priority=10,
        description="Eventbrite event platform with structured event data",
    )
    register_event_source(source)
```

**Exa registration** (`api/services/exa_client.py:408-421`):
```python
def register_exa_source() -> None:
    """Register Exa as an event source in the global registry."""
    from api.services.base import EventSource, register_event_source

    api_key = os.getenv("EXA_API_KEY", "")

    source = EventSource(
        name="exa",
        search_fn=search_events_adapter,
        is_enabled_fn=lambda: bool(api_key),
        priority=20,
        description="Exa neural web search for event discovery",
    )
    register_event_source(source)
```

**Grep search results confirm these functions are never called:**
```
register_eventbrite_source - only found at:
  - definition: eventbrite.py:472
  - exports: __init__.py:22, __init__.py:71

register_exa_source - only found at:
  - definition: exa_client.py:408
  - exports: __init__.py:29, __init__.py:80
```

Neither function is invoked anywhere in the codebase.

### The Search Flow

1. **index.py:186-197**: When `ready_to_search=True`, calls `search_events(profile)`
2. **search.py:207-208**: Gets registry and enabled sources:
   ```python
   registry = get_event_source_registry()
   enabled_sources = registry.get_enabled()
   ```
3. **search.py:210-219**: Early return if no sources:
   ```python
   if not enabled_sources:
       settings = get_settings()
       if not settings.has_event_source:
           logger.warning("No event sources enabled in registry")
           return SearchResult(
               events=[],
               source="unavailable",
               message="Event search is not currently available.",
           )
   ```

Since registration functions are never called, `enabled_sources` is always an empty list.

### Secondary Issue: SearchProfile Missing Time Window

The logs also show:
```
time_window=start=None end=None
```

Even if sources were registered, the clarifying agent is setting `ready_to_search=True` without properly populating the `time_window`. This would cause issues with date-based filtering in the adapters.

## Code References

- `api/services/base.py:109-111` - `get_enabled()` returns empty list when no sources registered
- `api/services/base.py:130-140` - Global registry singleton
- `api/services/eventbrite.py:472-486` - `register_eventbrite_source()` never called
- `api/services/exa_client.py:408-421` - `register_exa_source()` never called
- `api/agents/search.py:207-219` - Early return when `enabled_sources` is empty
- `api/index.py:186-197` - Search handoff trigger

## Architecture Documentation

### Expected Startup Flow (Not Implemented)

The design expects sources to be registered at application startup:

```python
# Expected in api/index.py or similar
from api.services import register_eventbrite_source, register_exa_source

# Register event sources on startup
register_eventbrite_source()
register_exa_source()
```

### Current State

The functions are exported for use but the application startup (`api/index.py`) does not call them. The registry remains empty throughout the application lifecycle.

## Open Questions

1. Was registration intentionally omitted during development?
2. Should registration happen in `api/index.py` on app startup or via a FastAPI lifecycle event?
3. Should the registry log more explicitly when it's empty vs when sources are disabled?
