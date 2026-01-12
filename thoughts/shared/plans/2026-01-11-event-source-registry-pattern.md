# Event Source Registry Pattern Implementation Plan

## Overview

This plan implements the Registry Pattern (Option B from the research document) for the event source architecture. This pattern enables dynamic source management, making it trivial to add new event sources (like Meetup GraphQL) without modifying the core search orchestration logic.

## Current State Analysis

### What Exists Now

The codebase has three event source clients following a **convention-based pattern**:

1. **EventbriteClient** (`api/services/eventbrite.py`)
   - Constructor: `__init__(api_key: str | None = None)` with env fallback
   - Search: `search_events(location, start_date, end_date, categories, free_only, page_size) -> list[EventbriteEvent]`
   - Singleton: `get_eventbrite_client()`

2. **ExaClient** (`api/services/exa_client.py`)
   - Constructor: `__init__(api_key: str | None = None)` with env fallback
   - Search: `search(query, num_results, include_text, ...) -> list[ExaSearchResult]`
   - Singleton: `get_exa_client()`

3. **FirecrawlClient/PoshExtractor** (`api/services/firecrawl.py`)
   - Scraping-based discovery, not search API
   - Used via cache, not directly in search flow

### Current Integration (Problem Area)

`api/agents/search.py:302-399` has **hardcoded source list**:
- Lines 335-336: `has_eventbrite = bool(settings.eventbrite_api_key)`
- Lines 343-349: Manual task building per source
- Each source requires adding code to `search_events()`

### Key Discoveries

- All clients follow the same constructor pattern with env fallback
- The search methods have **incompatible signatures** - this is fine, the fetcher functions handle translation
- `EventResult` is the unified output format (lines 28-40)
- `SearchProfile` is the unified input format (from `api/models/search.py`)
- Configuration is centralized in `api/config.py` via `Settings` class

## Desired End State

After implementation:

1. **Adding a new source** requires only:
   - Create client file (`api/services/meetup.py`)
   - Add config key to `Settings`
   - Register source at module load time

2. **No changes to `search_events()`** when adding sources

3. **Type-safe contracts** via Protocol definition

4. **Verification**:
   - `pytest api/services/tests/test_registry.py` passes
   - `pytest api/agents/tests/test_search.py` passes
   - `make lint` passes
   - Adding Meetup source requires zero changes to search.py

## What We're NOT Doing

- NOT implementing MeetupClient in this plan (separate follow-up work)
- NOT changing the existing client internals
- NOT refactoring existing fetch functions beyond integration
- NOT adding new functionality to the cache system
- NOT changing the EventResult model or SearchProfile model

## Implementation Approach

We'll use a **fetcher-based registry** rather than a client-based registry because:
1. Existing clients have incompatible search method signatures
2. The fetcher functions (`_fetch_eventbrite_events`, `_fetch_exa_events`) already handle translation
3. This minimizes changes to existing code

The registry will store:
- Source name (for attribution)
- Fetcher function (async callable)
- Config key (to check availability)

## Phase 1: Protocol and Registry Infrastructure

### Overview
Create the base infrastructure: Protocol definition for type safety and the registry data structure.

### Changes Required:

#### 1.1 Create Base Module

**File**: `api/services/base.py` (NEW FILE)
**Changes**: Create Protocol and Registry types

```python
"""Base protocols and registry for event sources."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from api.agents.search import EventResult
    from api.models import SearchProfile


@dataclass
class EventSource:
    """Registered event source configuration."""

    name: str  # e.g., "eventbrite", "exa", "meetup"
    fetcher: Callable[["SearchProfile"], Awaitable[list["EventResult"]]]
    config_key: str  # e.g., "eventbrite_api_key"
    description: str = ""  # Optional human-readable description


class EventSourceRegistry:
    """Registry for dynamically managing event sources."""

    def __init__(self) -> None:
        self._sources: dict[str, EventSource] = {}

    def register(self, source: EventSource) -> None:
        """Register an event source.

        Args:
            source: EventSource configuration to register
        """
        self._sources[source.name] = source

    def get(self, name: str) -> EventSource | None:
        """Get a registered source by name."""
        return self._sources.get(name)

    def get_available(self, settings: object) -> list[EventSource]:
        """Get all sources that have API keys configured.

        Args:
            settings: Settings object with API key attributes

        Returns:
            List of EventSource where the config_key has a truthy value
        """
        available = []
        for source in self._sources.values():
            if getattr(settings, source.config_key, None):
                available.append(source)
        return available

    def all_sources(self) -> list[EventSource]:
        """Get all registered sources regardless of availability."""
        return list(self._sources.values())


# Global registry instance
_registry = EventSourceRegistry()


def get_registry() -> EventSourceRegistry:
    """Get the global event source registry."""
    return _registry


def register_source(source: EventSource) -> None:
    """Register an event source to the global registry.

    Convenience function for use at module load time.
    """
    _registry.register(source)
```

#### 1.2 Export from Services Package

**File**: `api/services/__init__.py`
**Changes**: Add exports for base module

Add these imports at the top:
```python
from .base import (
    EventSource,
    EventSourceRegistry,
    get_registry,
    register_source,
)
```

Add to `__all__`:
```python
    "EventSource",
    "EventSourceRegistry",
    "get_registry",
    "register_source",
```

### Success Criteria:

#### Automated Verification:
- [ ] File exists: `api/services/base.py`
- [ ] Type checking passes: `mypy api/services/base.py`
- [ ] Linting passes: `ruff check api/services/`
- [ ] Import works: `python -c "from api.services import get_registry, register_source"`

#### Manual Verification:
- [ ] Review code structure matches the plan

**Implementation Note**: After completing this phase and automated verification passes, proceed to Phase 2.

---

## Phase 2: Migrate Existing Sources to Registry

### Overview
Register existing event sources (Eventbrite, Exa) with the registry without changing their implementation.

### Changes Required:

#### 2.1 Register Eventbrite Source

**File**: `api/services/eventbrite.py`
**Changes**: Add registration at module load time

Add import at top:
```python
from api.services.base import EventSource, register_source
```

Add at end of file (after singleton but before any `if __name__` block):
```python
def _create_eventbrite_source() -> None:
    """Register Eventbrite as an event source.

    Note: The fetcher is imported lazily to avoid circular imports.
    """
    # Lazy import to avoid circular dependency with search module
    from api.agents.search import _fetch_eventbrite_events

    register_source(
        EventSource(
            name="eventbrite",
            fetcher=_fetch_eventbrite_events,
            config_key="eventbrite_api_key",
            description="Eventbrite API for local events",
        )
    )


# Register on module import
_create_eventbrite_source()
```

#### 2.2 Register Exa Source

**File**: `api/services/exa_client.py`
**Changes**: Add registration at module load time

Add import at top:
```python
from api.services.base import EventSource, register_source
```

Add at end of file:
```python
def _create_exa_source() -> None:
    """Register Exa as an event source.

    Note: The fetcher is imported lazily to avoid circular imports.
    """
    from api.agents.search import _fetch_exa_events

    register_source(
        EventSource(
            name="exa",
            fetcher=_fetch_exa_events,
            config_key="exa_api_key",
            description="Exa AI-powered web search for events",
        )
    )


# Register on module import
_create_exa_source()
```

### Success Criteria:

#### Automated Verification:
- [ ] Import works without error: `python -c "from api.services import eventbrite, exa_client; from api.services import get_registry; r = get_registry(); print([s.name for s in r.all_sources()])"`
- [ ] Shows both sources: output should include `['eventbrite', 'exa']`
- [ ] Linting passes: `ruff check api/services/`
- [ ] Type checking passes: `mypy api/services/`

#### Manual Verification:
- [ ] Verify no circular import errors occur

**Implementation Note**: After completing this phase and automated verification passes, proceed to Phase 3.

---

## Phase 3: Update Search Orchestration to Use Registry

### Overview
Modify `search_events()` to use the registry instead of hardcoded source checks.

### Changes Required:

#### 3.1 Update search_events Function

**File**: `api/agents/search.py`
**Changes**: Use registry for source discovery

Update imports (around line 21):
```python
# Change:
from api.services import get_eventbrite_client, get_exa_client

# To:
from api.services import get_eventbrite_client, get_exa_client, get_registry
```

Replace lines 334-361 (the hardcoded source checking and task building) with:
```python
    # 2. Get available sources from registry
    registry = get_registry()
    available_sources = registry.get_available(settings)

    # 3. Fetch from APIs in parallel
    try:
        tasks = []
        source_names = []

        for source in available_sources:
            tasks.append(source.fetcher(profile))
            source_names.append(source.name)

        if tasks:
            # Query API sources in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, BaseException):
                    logger.warning("%s fetch failed: %s", source_names[i], result)
                elif isinstance(result, list) and result:
                    events_list: list[EventResult] = result
                    all_events.extend(events_list)
                    sources_used.append(source_names[i])
                    logger.info("%s returned %d events", source_names[i], len(events_list))
```

**Note**: The old lines 335-336 (`has_eventbrite`, `has_exa`) and 343-361 are replaced entirely.

#### 3.2 Ensure Source Registration Happens

**File**: `api/agents/search.py`
**Changes**: Import services to trigger registration

Add near the top (after other api.services imports):
```python
# Import to ensure sources are registered
import api.services.eventbrite  # noqa: F401
import api.services.exa_client  # noqa: F401
```

### Success Criteria:

#### Automated Verification:
- [ ] Existing tests pass: `pytest api/agents/tests/test_search.py -v`
- [ ] Type checking passes: `mypy api/agents/search.py`
- [ ] Linting passes: `ruff check api/agents/`
- [ ] Integration check: `python -c "from api.agents.search import search_events; print('OK')"`

#### Manual Verification:
- [ ] Run search manually and verify results come from both sources
- [ ] Verify source attribution still works in responses

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation that search still works correctly before proceeding.

---

## Phase 4: Add Registry Tests

### Overview
Add comprehensive tests for the registry pattern.

### Changes Required:

#### 4.1 Create Registry Tests

**File**: `api/services/tests/test_registry.py` (NEW FILE)
**Changes**: Add unit tests for registry

```python
"""Tests for event source registry."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from api.services.base import EventSource, EventSourceRegistry

if TYPE_CHECKING:
    from api.agents.search import EventResult
    from api.models import SearchProfile


class TestEventSourceRegistry:
    """Tests for EventSourceRegistry class."""

    def test_register_source(self) -> None:
        """Test registering a source."""
        registry = EventSourceRegistry()

        async def mock_fetcher(profile: "SearchProfile") -> list["EventResult"]:
            return []

        source = EventSource(
            name="test",
            fetcher=mock_fetcher,
            config_key="test_api_key",
        )

        registry.register(source)

        assert registry.get("test") == source
        assert "test" in [s.name for s in registry.all_sources()]

    def test_get_nonexistent_source(self) -> None:
        """Test getting a source that doesn't exist."""
        registry = EventSourceRegistry()
        assert registry.get("nonexistent") is None

    def test_get_available_with_keys(self) -> None:
        """Test get_available returns only configured sources."""
        registry = EventSourceRegistry()

        async def mock_fetcher(profile: "SearchProfile") -> list["EventResult"]:
            return []

        registry.register(EventSource(
            name="configured",
            fetcher=mock_fetcher,
            config_key="configured_api_key",
        ))
        registry.register(EventSource(
            name="not_configured",
            fetcher=mock_fetcher,
            config_key="missing_api_key",
        ))

        # Mock settings object
        settings = MagicMock()
        settings.configured_api_key = "some-key"
        settings.missing_api_key = ""

        available = registry.get_available(settings)

        assert len(available) == 1
        assert available[0].name == "configured"

    def test_get_available_with_no_keys(self) -> None:
        """Test get_available returns empty when no keys configured."""
        registry = EventSourceRegistry()

        async def mock_fetcher(profile: "SearchProfile") -> list["EventResult"]:
            return []

        registry.register(EventSource(
            name="source1",
            fetcher=mock_fetcher,
            config_key="api_key_1",
        ))

        settings = MagicMock()
        settings.api_key_1 = None

        available = registry.get_available(settings)
        assert available == []


class TestGlobalRegistry:
    """Tests for global registry integration."""

    def test_sources_registered_on_import(self) -> None:
        """Test that sources are registered when modules are imported."""
        from api.services import get_registry

        # Force import of source modules
        import api.services.eventbrite  # noqa: F401
        import api.services.exa_client  # noqa: F401

        registry = get_registry()
        source_names = [s.name for s in registry.all_sources()]

        assert "eventbrite" in source_names
        assert "exa" in source_names

    def test_registered_sources_have_required_fields(self) -> None:
        """Test that registered sources have all required fields."""
        from api.services import get_registry

        import api.services.eventbrite  # noqa: F401
        import api.services.exa_client  # noqa: F401

        registry = get_registry()

        for source in registry.all_sources():
            assert source.name, "Source must have a name"
            assert source.fetcher, "Source must have a fetcher"
            assert source.config_key, "Source must have a config_key"
            assert callable(source.fetcher), "Fetcher must be callable"
```

### Success Criteria:

#### Automated Verification:
- [ ] Tests pass: `pytest api/services/tests/test_registry.py -v`
- [ ] All tests pass: `pytest api/ -v`
- [ ] Linting passes: `ruff check api/services/tests/`

#### Manual Verification:
- [ ] Review test coverage is adequate

**Implementation Note**: After completing this phase, run the full test suite to ensure nothing is broken.

---

## Phase 5: Documentation Update

### Overview
Update the services module docstring to document the registry pattern.

### Changes Required:

#### 5.1 Update Services __init__ Docstring

**File**: `api/services/__init__.py`
**Changes**: Add documentation about registry pattern

Replace line 1 docstring:
```python
"""Services for Calendar Club backend.

Event Source Registry
---------------------
Event sources are registered dynamically using the registry pattern.
To add a new event source:

1. Create a client in api/services/<source>.py following existing patterns
2. Create a fetcher function in api/agents/search.py: _fetch_<source>_events()
3. Register at module load time:

    from api.services.base import EventSource, register_source

    def _create_source() -> None:
        from api.agents.search import _fetch_my_events
        register_source(EventSource(
            name="mysource",
            fetcher=_fetch_my_events,
            config_key="mysource_api_key",
            description="My event source",
        ))

    _create_source()

4. Add config key to Settings in api/config.py
5. Import your module in api/agents/search.py to ensure registration

The search orchestrator automatically discovers registered sources.
"""
```

### Success Criteria:

#### Automated Verification:
- [ ] Linting passes: `ruff check api/services/__init__.py`
- [ ] Module still imports: `python -c "from api.services import *; print('OK')"`

#### Manual Verification:
- [ ] Documentation is clear and accurate

---

## Testing Strategy

### Unit Tests:
- Registry operations (register, get, get_available)
- Source registration at import time
- Missing config key handling

### Integration Tests:
- Full search flow uses registry
- Source attribution correct
- Graceful handling of unavailable sources

### Manual Testing Steps:
1. Run search with both API keys configured
2. Verify results from both sources appear
3. Run search with only one API key configured
4. Verify only that source appears in results
5. Run search with no API keys configured
6. Verify appropriate error message

## Performance Considerations

- Registry lookup is O(n) where n = number of sources (expected <10)
- Import-time registration has negligible startup cost
- No runtime overhead compared to current hardcoded approach

## Migration Notes

- Backward compatible: existing code continues to work
- Sources registered at import time, no manual setup needed
- Old hardcoded checks can be removed once registry is in use

## Future: Adding Meetup Source

With the registry pattern in place, adding Meetup requires only:

1. Create `api/services/meetup.py` with `MeetupClient`
2. Add `meetup_api_key: str = Field(default="", ...)` to `Settings`
3. Create `_fetch_meetup_events()` in `api/agents/search.py`
4. Register source in `meetup.py`:
   ```python
   register_source(EventSource(
       name="meetup",
       fetcher=_fetch_meetup_events,
       config_key="meetup_api_key",
   ))
   ```
5. Import `api.services.meetup` in `search.py`

**Zero changes to `search_events()` function.**

## References

- Original research: `throughts/shared/research/2026-01-11-meetup-graphql-integration.md`
- EventbriteClient pattern: `api/services/eventbrite.py:46-62`
- Search orchestration: `api/agents/search.py:302-399`
- Configuration: `api/config.py`
