"""Services for Calendar Club backend."""

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
