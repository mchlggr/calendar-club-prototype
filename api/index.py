"""
FastAPI backend for Calendar Club.

Provides streaming chat endpoint for discovery conversations
using OpenAI Agents SDK.
"""

import json
import logging
from typing import Any, AsyncGenerator

from agents import Runner
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from api.agents import clarifying_agent
from api.config import configure_logging, get_settings

from api.services import CalendarEvent, create_ics_event, create_ics_multiple

configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title="Calendar Club API",
    description="Event discovery through conversational AI",
    version="0.1.0",
)

# CORS configuration from environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    """Request body for simple chat endpoint."""

    message: str


class ChatStreamRequest(BaseModel):
    """Request body for streaming chat endpoint."""

    session_id: str
    message: str


@app.get("/")
def root():
    """Root endpoint."""
    return {"status": "ok"}


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/api/chat/stream")
async def chat_stream(request: ChatStreamRequest) -> StreamingResponse:
    """
    Stream chat responses using Server-Sent Events.

    The ClarifyingAgent will ask questions to build a SearchProfile.
    Events are streamed as they occur:
    - type: "text" - Text content from the agent
    - type: "phase" - Agent handoff occurred
    - type: "action" - Tool was called
    - type: "events" - Event results from search
    - type: "complete" - Response finished
    - type: "error" - An error occurred
    """

    def _to_jsonable(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump()
        if isinstance(value, list):
            return [_to_jsonable(item) for item in value]
        if isinstance(value, dict):
            return {key: _to_jsonable(val) for key, val in value.items()}
        return value

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            active_settings = get_settings()

            # Check for API key
            if not active_settings.openai_api_key:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Service temporarily unavailable'})}\n\n"
                logger.error("OPENAI_API_KEY not configured")
                return

            session_label = request.session_id[:8] if request.session_id else "unknown"
            logger.info("Chat stream started for session: %s", session_label)

            # Run agent with streaming
            streaming_result = Runner.run_streamed(
                clarifying_agent,
                input=request.message,
                context={"session_id": request.session_id},
            )

            async for event in streaming_result.stream_events():
                if event.type == "raw_response_event":
                    # Text content from the model
                    if hasattr(event.data, "delta") and event.data.delta:
                        yield f"data: {json.dumps({'type': 'text', 'content': event.data.delta})}\n\n"
                elif event.type == "agent_updated_stream_event":
                    # Agent handoff occurred
                    agent_name = event.new_agent.name if event.new_agent else "unknown"
                    logger.info("Agent handoff to: %s", agent_name)
                    yield f"data: {json.dumps({'type': 'phase', 'agent': agent_name})}\n\n"
                elif event.type == "run_item_stream_event":
                    if hasattr(event.item, "type"):
                        if event.item.type == "tool_call_item":
                            tool_name = getattr(event.item, "name", "unknown")
                            logger.info("Tool call: %s", tool_name)
                            yield f"data: {json.dumps({'type': 'action', 'tool': tool_name})}\n\n"
                        elif event.item.type == "tool_call_output_item":
                            # Stream the tool output (event results)
                            output = getattr(event.item, "output", None)
                            if output:
                                serialized_output = _to_jsonable(output)
                                try:
                                    json.dumps(serialized_output)
                                    yield f"data: {json.dumps({'type': 'events', 'data': serialized_output})}\n\n"
                                except (TypeError, ValueError) as exc:
                                    logger.warning("Tool output not JSON-serializable: %s", exc)

            # Signal completion
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"
            logger.info("Chat stream completed for session: %s", session_label)

        except Exception as e:
            logger.exception("Chat stream error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'error': 'Something went wrong. Please try again.'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class ExportEventsRequest(BaseModel):
    events: list[CalendarEvent]


@app.post("/api/calendar/export")
def export_calendar(event: CalendarEvent):
    """Export a single event as ICS file."""
    ics_content = create_ics_event(event)
    filename = f"{event.title.replace(' ', '-').lower()}.ics"

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/calendar/export-multiple")
def export_calendar_multiple(request: ExportEventsRequest):
    """Export multiple events as a single ICS file."""
    if not request.events:
        raise HTTPException(status_code=400, detail="No events provided")

    ics_content = create_ics_multiple(request.events)

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="calendar-club-events.ics"'},
    )


@app.post("/api/chat")
def chat(request: ChatRequest):
    """Simple non-streaming chat endpoint (legacy)."""
    if not get_settings().openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    # For now, return a simple message
    return {"reply": "Please use the /api/chat/stream endpoint for the full experience."}
