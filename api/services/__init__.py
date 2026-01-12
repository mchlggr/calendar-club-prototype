"""Services for Calendar Club backend."""

from .background_tasks import BackgroundTaskManager, get_background_task_manager
from .base import (
    EventSource,
    EventSourceRegistry,
    get_event_source_registry,
    register_event_source,
)
from .calendar import CalendarEvent, create_ics_event, create_ics_multiple
from .event_cache import (
    CachedEvent,
    EventCache,
    EventCacheService,
    get_event_cache,
    init_event_cache,
)
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
from .exa_research import (
    ExaResearchClient,
    ExaResearchResult,
    get_exa_research_client,
    register_exa_research_source,
)
from .firecrawl import (
    BaseExtractor,
    FirecrawlClient,
    LumaEvent,
    LumaExtractor,
    PoshExtractor,
    ScrapedEvent,
    get_firecrawl_client,
    get_posh_extractor,
    register_posh_source,
)
from .google_calendar import (
    GoogleCalendarEvent,
    GoogleCalendarService,
    get_google_calendar_service,
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
from .sse_connections import SSEConnection, SSEConnectionManager, get_sse_manager
from .temporal_parser import TemporalParser, TemporalResult

__all__ = [
    "BackgroundTaskManager",
    "get_background_task_manager",
    "CalendarEvent",
    "create_ics_event",
    "create_ics_multiple",
    "CachedEvent",
    "EventCache",
    "EventCacheService",
    "get_event_cache",
    "init_event_cache",
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
    "ExaResearchClient",
    "ExaResearchResult",
    "get_exa_research_client",
    "register_exa_research_source",
    "BaseExtractor",
    "FirecrawlClient",
    "LumaEvent",
    "LumaExtractor",
    "PoshExtractor",
    "ScrapedEvent",
    "get_firecrawl_client",
    "get_posh_extractor",
    "register_posh_source",
    "GoogleCalendarEvent",
    "GoogleCalendarService",
    "get_google_calendar_service",
    "MSGraphAuth",
    "OutlookCalendarClient",
    "OutlookEvent",
    "TokenInfo",
    "get_msgraph_auth",
    "get_outlook_client",
    "SessionManager",
    "get_session_manager",
    "init_session_manager",
    "SSEConnection",
    "SSEConnectionManager",
    "get_sse_manager",
    "TemporalParser",
    "TemporalResult",
]
