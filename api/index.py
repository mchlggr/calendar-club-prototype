"""
FastAPI backend for Calendar Club.

Provides streaming chat endpoint for discovery conversations
using OpenAI Agents SDK.
"""

import json
import logging
import os
from typing import AsyncGenerator

from agents import Runner
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.agents import clarifying_agent

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("calendarclub.api")

app = FastAPI(
    title="Calendar Club API",
    description="Event discovery through conversational AI",
    version="0.1.0",
)

# CORS for local development and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


def _safe_json_serialize(data: object) -> str | None:
    """Safely serialize data to JSON, returning None if not serializable."""
    try:
        return json.dumps(data)
    except (TypeError, ValueError):
        return None


def _format_user_error(error: Exception) -> str:
    """Convert internal errors to user-friendly messages."""
    error_str = str(error).lower()

    if "api key" in error_str or "authentication" in error_str:
        return "Service configuration issue. Please try again later."
    if "timeout" in error_str:
        return "Request timed out. Please try again."
    if "rate limit" in error_str:
        return "Service is busy. Please wait a moment and try again."

    # Generic fallback - don't expose internal details
    return "Something went wrong. Please try again."


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
    session_id = request.session_id
    logger.info("Chat stream started for session %s", session_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Check for API key
            if not os.getenv("OPENAI_API_KEY"):
                logger.error("OPENAI_API_KEY not configured for session %s", session_id)
                yield f"data: {json.dumps({'type': 'error', 'content': 'Service configuration issue. Please try again later.'})}\n\n"
                return

            logger.debug("Running agent for session %s with message: %s", session_id, request.message[:100])

            # Run agent with streaming
            streaming_result = Runner.run_streamed(
                clarifying_agent,
                input=request.message,
            )

            async for event in streaming_result.stream_events():
                if event.type == "raw_response_event":
                    # Text content from the model
                    if hasattr(event.data, "delta") and event.data.delta:
                        yield f"data: {json.dumps({'type': 'text', 'content': event.data.delta})}\n\n"
                elif event.type == "agent_updated_stream_event":
                    # Agent handoff occurred
                    logger.info("Agent handoff to %s for session %s", event.new_agent.name, session_id)
                    yield f"data: {json.dumps({'type': 'phase', 'agent': event.new_agent.name})}\n\n"
                elif event.type == "run_item_stream_event":
                    if hasattr(event.item, "type"):
                        if event.item.type == "tool_call_item":
                            tool_name = getattr(event.item, "name", "unknown")
                            logger.debug("Tool call: %s for session %s", tool_name, session_id)
                            yield f"data: {json.dumps({'type': 'action', 'tool': tool_name})}\n\n"
                        elif event.item.type == "tool_call_output_item":
                            # Stream the tool output (event results)
                            output = getattr(event.item, "output", None)
                            if output:
                                # Validate JSON serializable before streaming
                                serialized = _safe_json_serialize({"type": "events", "data": output})
                                if serialized:
                                    yield f"data: {serialized}\n\n"
                                else:
                                    logger.warning("Non-serializable tool output for session %s", session_id)

            # Signal completion
            logger.info("Chat stream completed for session %s", session_id)
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            # Log full error internally, send sanitized message to user
            logger.exception("Error in chat stream for session %s", session_id)
            user_message = _format_user_error(e)
            yield f"data: {json.dumps({'type': 'error', 'content': user_message})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat")
def chat(request: ChatRequest):
    """Simple non-streaming chat endpoint (legacy)."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    # For now, return a simple message
    return {"reply": "Please use the /api/chat/stream endpoint for the full experience."}
