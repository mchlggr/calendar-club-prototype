"""
Services for Calendar Club backend.

This module provides service clients and utilities for event discovery,
calendar management, and real-time communication.

Event Source Registry
---------------------
The event source registry allows pluggable event sources to be registered
and queried dynamically. Sources are searched in parallel during event
discovery.

Registering a source at startup::

    from api.services import register_eventbrite_source, register_exa_source

    # Register built-in sources
    register_eventbrite_source()
    register_exa_source()

Creating a custom event source::

    from api.services import EventSource, register_event_source

    async def my_search(profile):
        # Implement search logic
        return [...]

    source = EventSource(
        name="my_source",
        search_fn=my_search,
        is_enabled_fn=lambda: bool(os.getenv("MY_API_KEY")),
        priority=50,  # Lower = higher priority
        description="My custom event source",
    )
    register_event_source(source)

Querying enabled sources::

    from api.services import get_event_source_registry

    registry = get_event_source_registry()
    for source in registry.get_enabled():
        results = await source.search_fn(profile)

Available Services
------------------
- EventSource, EventSourceRegistry: Pluggable event source pattern
- EventbriteClient: Eventbrite API integration
- ExaClient: Exa neural web search
- CalendarEvent: ICS calendar generation
- SessionManager: Conversation session management
- SSEConnectionManager: Server-sent events
- TemporalParser: Natural language date/time parsing
"""

from .background_tasks import BackgroundTaskManager, get_background_task_manager
from .base import (
    EventSource,
    EventSourceRegistry,
    get_event_source_registry,
    register_event_source,
)
from .calendar import CalendarEvent, create_ics_event, create_ics_multiple
from .eventbrite import (
    EventbriteClient,
    EventbriteEvent,
    get_eventbrite_client,
    register_eventbrite_source,
)
from .exa_client import (
    ExaClient,
    ExaSearchResult,
    ExaWebset,
    get_exa_client,
    register_exa_source,
)
from .session import SessionManager, get_session_manager, init_session_manager
from .sse_connections import SSEConnection, SSEConnectionManager, get_sse_manager
from .temporal_parser import TemporalParser, TemporalResult

__all__ = [
    "BackgroundTaskManager",
    "get_background_task_manager",
    "CalendarEvent",
    "create_ics_event",
    "create_ics_multiple",
    "EventbriteClient",
    "EventbriteEvent",
    "get_eventbrite_client",
    "register_eventbrite_source",
    "EventSource",
    "EventSourceRegistry",
    "get_event_source_registry",
    "register_event_source",
    "ExaClient",
    "ExaSearchResult",
    "ExaWebset",
    "get_exa_client",
    "register_exa_source",
    "SessionManager",
    "get_session_manager",
    "init_session_manager",
    "SSEConnection",
    "SSEConnectionManager",
    "get_sse_manager",
    "TemporalParser",
    "TemporalResult",
]
