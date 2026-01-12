"""API endpoints for Calendar Club discovery chat."""

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel

from agents import Runner, SQLiteSession

from api.agents import clarifying_agent
from api.agents.search import search_events
from api.config import configure_logging, get_settings
from api.services import (
    register_eventbrite_source,
    register_exa_source,
)
from api.services.exa_research import register_exa_research_source
from api.services.firecrawl import register_posh_source
from api.services.meetup import register_meetup_source
from api.services.background_tasks import get_background_task_manager
from api.services.calendar import CalendarEvent, create_ics_event, create_ics_multiple
from api.services.google_calendar import (
    GoogleCalendarEvent,
    get_google_calendar_service,
)
from api.services.session import get_session_manager
from api.services.sse_connections import get_sse_manager

load_dotenv()

# Configure logging from settings (uses LOG_LEVEL env var)
configure_logging()
logger = logging.getLogger(__name__)

# Register event sources
register_eventbrite_source()
# register_meetup_source()
register_exa_source()
register_posh_source()
register_exa_research_source()


def _safe_json_serialize(data: Any) -> str | None:
    """Safely serialize data to JSON, returning None if not serializable."""
    try:
        return json.dumps(data)
    except (TypeError, ValueError):
        return None


def _format_user_error(error: Exception) -> str:
    """Format an exception into a user-friendly error message."""
    error_str = str(error).lower()

    if "api key" in error_str or "invalid" in error_str:
        return "There's a configuration issue. Please try again later."
    elif "timeout" in error_str:
        return "The request timed out. Please try again."
    elif "rate limit" in error_str:
        return "We're a bit busy right now. Please try again in a moment."
    else:
        return "Something went wrong. Please try again."


app = FastAPI()

# CORS configuration from environment
ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://localhost:3001"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_openai_client() -> OpenAI:
    """Lazy-initialize OpenAI client to allow server boot without API key."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
    return OpenAI(api_key=api_key)


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    message: str
    conversation_id: str | None = None


class ConversationMessage(BaseModel):
    """A message in the conversation history."""

    role: str
    content: str


class ChatStreamRequest(BaseModel):
    """Request body for streaming chat endpoint."""

    message: str
    session_id: str | None = None
    history: list[ConversationMessage] = []


class ExportMultipleRequest(BaseModel):
    """Request body for exporting multiple events."""

    events: list[CalendarEvent]


def sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event with type included in payload."""
    # Include type in the JSON payload so frontend can access it
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload)}\n\n"


async def stream_chat_response(
    message: str, session: SQLiteSession | None = None, session_id: str | None = None
) -> AsyncGenerator[str, None]:
    """Stream chat response with automatic handoff from clarifying to search phase.

    The flow:
    1. ClarifyingAgent gathers user preferences
    2. When ready_to_search=True, handoff to search phase
    3. SearchAgent presents results and handles refinement
    4. Background Websets discovery pushes more_events later
    """
    # Generate trace ID for this request
    trace_id = str(uuid.uuid4())[:8]  # Short trace ID for readability

    sse_manager = get_sse_manager()
    bg_manager = get_background_task_manager()
    settings = get_settings()
    connection = None

    logger.debug(
        "🔍 [Chat] Request started | trace=%s session=%s",
        trace_id,
        session_id or "None",
    )

    # Register SSE connection for background event delivery
    if session_id:
        connection = await sse_manager.register(session_id)
        logger.debug(
            "💬 [Chat] Message received | trace=%s session=%s length=%d msg=%s",
            trace_id,
            session_id,
            len(message),
            message[:50],
        )
    else:
        logger.debug(
            "💬 [Chat] Message received | trace=%s session=None length=%d msg=%s",
            trace_id,
            len(message),
            message[:50],
        )

    try:
        # Phase 1: Run ClarifyingAgent to gather/refine preferences
        logger.debug(
            "🤔 [Clarify] Agent starting | trace=%s session=%s",
            trace_id,
            session_id or "None",
        )
        clarify_start = time.perf_counter()
        result = await Runner.run(
            clarifying_agent,
            message,
            session=session,
        )
        clarify_elapsed = time.perf_counter() - clarify_start
        logger.debug(
            "✅ [Clarify] Agent complete | trace=%s duration=%.2fs ready_to_search=%s",
            trace_id,
            clarify_elapsed,
            result.final_output.ready_to_search if result.final_output else False,
        )

        # Stream the clarifying agent's message content
        if result.final_output:
            output = result.final_output
            message_text = output.message

            # Stream message in chunks for responsiveness
            for i in range(0, len(message_text), 10):
                chunk = message_text[i : i + 10]
                yield sse_event("content", {"content": chunk})

            # Send quick picks if any
            if output.quick_picks:
                quick_picks_data = [
                    {"label": qp.label, "value": qp.value} for qp in output.quick_picks
                ]
                yield sse_event("quick_picks", {"quick_picks": quick_picks_data})

            # Send placeholder if provided
            if output.placeholder:
                yield sse_event("placeholder", {"placeholder": output.placeholder})

            # Phase 2: Handoff to search when ready
            if output.ready_to_search and output.search_profile:
                profile = output.search_profile
                logger.debug(
                    "🔍 [Search] Handoff | trace=%s categories=%s time_window=%s keywords=%s",
                    trace_id,
                    profile.categories,
                    profile.time_window,
                    profile.keywords[:3] if profile.keywords else None,
                )
                yield sse_event("searching", {})

                # Perform the search
                search_result = await search_events(output.search_profile)

                # Emit search results
                if search_result.events:
                    events_data = [
                        {
                            "id": evt.id,
                            "title": evt.title,
                            "startTime": evt.date,
                            "location": evt.location,
                            "categories": [evt.category],
                            "url": evt.url,
                            "source": search_result.source,
                        }
                        for evt in search_result.events
                    ]
                    # Log individual events before streaming
                    if logger.isEnabledFor(logging.DEBUG):
                        for ev in events_data:
                            ev_id = str(ev.get("id", "none"))[:20]
                            ev_title = str(ev.get("title", "untitled"))[:50]
                            logger.debug(
                                "📋 [SSE] Streaming event | trace=%s session=%s id=%s title=%s",
                                trace_id,
                                session_id or "None",
                                ev_id,
                                ev_title,
                            )
                    yield sse_event("events", {"events": events_data, "trace_id": trace_id})
                    logger.debug(
                        "📤 [SSE] Streaming events | trace=%s session=%s count=%d",
                        trace_id,
                        session_id or "None",
                        len(events_data),
                    )

                    # Emit a message about results from SearchAgent perspective
                    result_message = f"\n\nI found {len(search_result.events)} events for you!"
                    if search_result.source == "unavailable":
                        result_message = "\n\nEvent search is temporarily unavailable. Please try again later."

                    for i in range(0, len(result_message), 10):
                        chunk = result_message[i : i + 10]
                        yield sse_event("content", {"content": chunk})

                    # Start background Websets discovery if Exa is configured
                    if session_id and settings.exa_api_key:
                        webset_id = await bg_manager.start_webset_discovery(
                            session_id=session_id,
                            profile=output.search_profile,
                        )
                        if webset_id:
                            yield sse_event(
                                "background_search",
                                {"message": "Searching for more events in the background..."},
                            )
                else:
                    # No results found
                    logger.debug(
                        "📭 [Search] No results | trace=%s session=%s",
                        trace_id,
                        session_id or "None",
                    )
                    no_results_msg = "\n\nI couldn't find any events matching your criteria. "
                    if search_result.message:
                        no_results_msg += search_result.message
                    else:
                        no_results_msg += "Try broadening your search or changing the dates."

                    for i in range(0, len(no_results_msg), 10):
                        chunk = no_results_msg[i : i + 10]
                        yield sse_event("content", {"content": chunk})

        logger.debug("✅ [SSE] Stream complete | trace=%s session=%s", trace_id, session_id or "None")
        yield sse_event("done", {})

        # Keep connection alive briefly to receive background events
        if connection and session_id:
            try:
                # Wait for background events for a short time
                while True:
                    try:
                        event = await asyncio.wait_for(
                            connection.queue.get(),
                            timeout=0.5,
                        )
                        yield sse_event(event["type"], event)
                    except asyncio.TimeoutError:
                        # No more events, check if we should keep waiting
                        if not connection.active:
                            break
                        # Small poll window, then exit
                        break
            except Exception as e:
                logger.debug("Background event loop ended: %s", e)

    except Exception as e:
        logger.error("Error in stream_chat_response: %s", e, exc_info=True)
        yield sse_event("error", {"message": _format_user_error(e)})
        yield sse_event("done", {})
    finally:
        # Unregister connection
        if session_id:
            await sse_manager.unregister(session_id)


@app.get("/")
def root():
    """Root endpoint."""
    return {"status": "ok"}


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/api/chat")
def chat(request: ChatRequest):
    """Non-streaming chat endpoint (legacy)."""
    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a friendly event discovery assistant.",
                },
                {"role": "user", "content": request.message},
            ],
        )
        return {"reply": response.choices[0].message.content}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error calling OpenAI API: {str(e)}"
        ) from e


async def _error_stream(message: str) -> AsyncGenerator[str, None]:
    """Stream an error event."""
    yield sse_event("error", {"message": message})
    yield sse_event("done", {})


@app.post("/api/chat/stream")
async def chat_stream(request: ChatStreamRequest):
    """Streaming chat endpoint using Server-Sent Events with LLM-orchestrated quick picks."""
    # Log session_id if provided
    if request.session_id:
        logger.info("Chat stream request for session: %s", request.session_id)

    # Handle missing API key gracefully with error event stream
    if not os.getenv("OPENAI_API_KEY"):
        return StreamingResponse(
            _error_stream("OpenAI API key not configured. Please check server configuration."),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Get session for conversation history persistence
    session = None
    if request.session_id:
        session_manager = get_session_manager()
        session = session_manager.get_session(request.session_id)

    return StreamingResponse(
        stream_chat_response(request.message, session, request.session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/calendar/export")
def export_calendar(event: CalendarEvent):
    """Export a single event as ICS file."""
    ics_content = create_ics_event(event)
    return StreamingResponse(
        iter([ics_content]),
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=event.ics"},
    )


@app.post("/api/calendar/export-multiple")
def export_calendar_multiple(request: ExportMultipleRequest):
    """Export multiple events as ICS file."""
    if not request.events:
        raise HTTPException(status_code=400, detail="No events provided")

    ics_content = create_ics_multiple(request.events)
    return StreamingResponse(
        iter([ics_content]),
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=events.ics"},
    )


# Google Calendar OAuth endpoints


class GoogleAuthRequest(BaseModel):
    """Request body for Google OAuth initiation."""

    user_id: str
    redirect_url: str | None = None


class GoogleEventRequest(BaseModel):
    """Request body for creating a Google Calendar event."""

    user_id: str
    event: GoogleCalendarEvent


class GoogleEventsRequest(BaseModel):
    """Request body for creating multiple Google Calendar events."""

    user_id: str
    events: list[GoogleCalendarEvent]


@app.post("/api/google/auth")
def google_auth_start(request: GoogleAuthRequest):
    """Start Google OAuth flow.

    Returns the authorization URL that the user should be redirected to.
    """
    service = get_google_calendar_service()

    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Google Calendar integration is not configured",
        )

    try:
        auth_url = service.get_authorization_url(
            user_id=request.user_id,
            redirect_url=request.redirect_url,
        )
        return {"authorization_url": auth_url}
    except Exception as e:
        logger.error("Failed to start Google OAuth: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/google/callback")
def google_auth_callback(code: str, state: str):
    """Handle Google OAuth callback.

    Exchanges the authorization code for tokens and stores them.
    """
    service = get_google_calendar_service()

    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Google Calendar integration is not configured",
        )

    try:
        user_id, redirect_url = service.handle_oauth_callback(code=code, state=state)
        return {
            "success": True,
            "user_id": user_id,
            "redirect_url": redirect_url,
        }
    except Exception as e:
        logger.error("Google OAuth callback failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/google/status/{user_id}")
def google_auth_status(user_id: str):
    """Check if a user has valid Google Calendar credentials."""
    service = get_google_calendar_service()

    if not service.is_configured():
        return {
            "configured": False,
            "authenticated": False,
        }

    return {
        "configured": True,
        "authenticated": service.has_valid_credentials(user_id),
    }


@app.delete("/api/google/revoke/{user_id}")
def google_auth_revoke(user_id: str):
    """Revoke Google Calendar credentials for a user."""
    service = get_google_calendar_service()
    revoked = service.revoke_credentials(user_id)
    return {"revoked": revoked}


@app.post("/api/google/calendar/event")
def create_google_event(request: GoogleEventRequest):
    """Create an event in the user's Google Calendar."""
    service = get_google_calendar_service()

    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Google Calendar integration is not configured",
        )

    if not service.has_valid_credentials(request.user_id):
        raise HTTPException(
            status_code=401,
            detail="User has not authenticated with Google Calendar",
        )

    try:
        result = service.create_event(request.user_id, request.event)
        return {
            "success": True,
            "event_id": result.get("id"),
            "html_link": result.get("htmlLink"),
        }
    except Exception as e:
        logger.error("Failed to create Google Calendar event: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/google/calendar/events")
def create_google_events(request: GoogleEventsRequest):
    """Create multiple events in the user's Google Calendar."""
    service = get_google_calendar_service()

    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Google Calendar integration is not configured",
        )

    if not service.has_valid_credentials(request.user_id):
        raise HTTPException(
            status_code=401,
            detail="User has not authenticated with Google Calendar",
        )

    try:
        results = service.create_events_batch(request.user_id, request.events)
        return {
            "success": True,
            "created": len([r for r in results if "id" in r]),
            "failed": len([r for r in results if "error" in r]),
            "events": results,
        }
    except Exception as e:
        logger.error("Failed to create Google Calendar events: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
