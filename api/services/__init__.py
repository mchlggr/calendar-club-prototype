"""Services for Calendar Club backend."""

from .calendar import CalendarEvent, create_ics_event, create_ics_multiple
from .event_cache import (
    CachedEvent,
    EventCache,
    get_event_cache,
    init_event_cache,
)
from .eventbrite import EventbriteClient, EventbriteEvent, get_eventbrite_client
from .firecrawl import (
    FirecrawlClient,
    PoshExtractor,
    ScrapedEvent,
    get_firecrawl_client,
    get_posh_extractor,
)
from .msgraph import (
    MSGraphAuth,
    OutlookCalendarClient,
    OutlookEvent,
    TokenInfo,
    get_msgraph_auth,
    get_outlook_client,
)
from .session import SessionManager, get_session_manager, init_session_manager
from .temporal_parser import TemporalParser, TemporalResult

__all__ = [
    "CachedEvent",
    "CalendarEvent",
    "create_ics_event",
    "create_ics_multiple",
    "EventbriteClient",
    "EventbriteEvent",
    "EventCache",
    "FirecrawlClient",
    "get_event_cache",
    "get_eventbrite_client",
    "get_firecrawl_client",
    "get_msgraph_auth",
    "get_outlook_client",
    "get_posh_extractor",
    "init_event_cache",
    "MSGraphAuth",
    "OutlookCalendarClient",
    "OutlookEvent",
    "PoshExtractor",
    "ScrapedEvent",
    "SessionManager",
    "get_session_manager",
    "init_session_manager",
    "TemporalParser",
    "TemporalResult",
    "TokenInfo",
]
