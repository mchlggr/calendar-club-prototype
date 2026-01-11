"""API endpoints for Calendar Club discovery chat."""

import json
import logging
import os
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
from api.services.calendar import CalendarEvent, create_ics_event, create_ics_multiple
from api.services.session import get_session_manager

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    message: str, session: SQLiteSession | None = None
) -> AsyncGenerator[str, None]:
    """Stream chat response with automatic handoff from clarifying to search phase.

    The flow:
    1. ClarifyingAgent gathers user preferences
    2. When ready_to_search=True, handoff to search phase
    3. SearchAgent presents results and handles refinement
    """
    try:
        # Phase 1: Run ClarifyingAgent to gather/refine preferences
        logger.info("Running ClarifyingAgent for message: %s", message[:50])
        result = await Runner.run(
            clarifying_agent,
            message,
            session=session,
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

            # Phase 2: Handoff to search when ready
            if output.ready_to_search and output.search_profile:
                logger.info("Handoff to search phase with profile: %s", output.search_profile)
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
                    yield sse_event("events", {"events": events_data})

                    # Emit a message about results from SearchAgent perspective
                    result_message = f"\n\nI found {len(search_result.events)} events for you!"
                    if search_result.source == "demo":
                        result_message += " (These are sample events for demonstration.)"
                    elif search_result.source == "unavailable":
                        result_message = "\n\nEvent search is temporarily unavailable. Please try again later."

                    for i in range(0, len(result_message), 10):
                        chunk = result_message[i : i + 10]
                        yield sse_event("content", {"content": chunk})
                else:
                    # No results found
                    no_results_msg = "\n\nI couldn't find any events matching your criteria. "
                    if search_result.message:
                        no_results_msg += search_result.message
                    else:
                        no_results_msg += "Try broadening your search or changing the dates."

                    for i in range(0, len(no_results_msg), 10):
                        chunk = no_results_msg[i : i + 10]
                        yield sse_event("content", {"content": chunk})

        yield sse_event("done", {})

    except Exception as e:
        logger.error("Error in stream_chat_response: %s", e, exc_info=True)
        yield sse_event("error", {"message": _format_user_error(e)})
        yield sse_event("done", {})


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
        stream_chat_response(request.message, session),
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
