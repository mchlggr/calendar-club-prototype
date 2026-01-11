"""Services for Calendar Club backend."""

from .base import EventSource, EventSourceRegistry, event_registry
from .calendar import CalendarEvent, create_ics_event, create_ics_multiple
from .event_cache import CachedEvent, EventCacheService, get_event_cache
from .eventbrite import EventbriteClient, EventbriteEvent, get_eventbrite_client
from .firecrawl import FirecrawlClient, LumaEvent, LumaExtractor, get_firecrawl_client
from .google_calendar import (
    GoogleCalendarEvent,
    GoogleCalendarService,
    get_google_calendar_service,
)
from .session import SessionManager, get_session_manager, init_session_manager
from .temporal_parser import TemporalParser, TemporalResult

__all__ = [
    "EventSource",
    "EventSourceRegistry",
    "event_registry",
    "CalendarEvent",
    "create_ics_event",
    "create_ics_multiple",
    "CachedEvent",
    "EventCacheService",
    "get_event_cache",
    "EventbriteClient",
    "EventbriteEvent",
    "get_eventbrite_client",
    "FirecrawlClient",
    "LumaEvent",
    "LumaExtractor",
    "get_firecrawl_client",
    "GoogleCalendarEvent",
    "GoogleCalendarService",
    "get_google_calendar_service",
    "SessionManager",
    "get_session_manager",
    "init_session_manager",
    "TemporalParser",
    "TemporalResult",
]
