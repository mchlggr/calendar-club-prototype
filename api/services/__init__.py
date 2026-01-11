"""Services for Calendar Club backend."""

from .background_tasks import BackgroundTaskManager, get_background_task_manager
from .calendar import CalendarEvent, create_ics_event, create_ics_multiple
from .event_cache import CachedEvent, EventCacheService, get_event_cache
from .eventbrite import EventbriteClient, EventbriteEvent, get_eventbrite_client
from .exa_client import ExaClient, ExaSearchResult, ExaWebset, get_exa_client
from .firecrawl import FirecrawlClient, LumaEvent, LumaExtractor, get_firecrawl_client
from .session import SessionManager, get_session_manager, init_session_manager
from .sse_connections import SSEConnection, SSEConnectionManager, get_sse_manager
from .temporal_parser import TemporalParser, TemporalResult

__all__ = [
    "BackgroundTaskManager",
    "get_background_task_manager",
    "CalendarEvent",
    "create_ics_event",
    "create_ics_multiple",
    "CachedEvent",
    "EventCacheService",
    "get_event_cache",
    "EventbriteClient",
    "EventbriteEvent",
    "get_eventbrite_client",
    "ExaClient",
    "ExaSearchResult",
    "ExaWebset",
    "get_exa_client",
    "FirecrawlClient",
    "LumaEvent",
    "LumaExtractor",
    "get_firecrawl_client",
    "SessionManager",
    "get_session_manager",
    "init_session_manager",
    "SSEConnection",
    "SSEConnectionManager",
    "get_sse_manager",
    "TemporalParser",
    "TemporalResult",
]
