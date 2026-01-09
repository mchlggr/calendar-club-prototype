"""
FastAPI backend for Calendar Club.

Provides streaming chat endpoint for discovery conversations
using OpenAI Agents SDK.
"""

import json
from typing import AsyncGenerator

from agents import Runner
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.agents import clarifying_agent
from backend.services import session_manager

app = FastAPI(
    title="Calendar Club API",
    description="Event discovery through conversational AI",
    version="0.1.0",
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    message: str
    session_id: str


class ChatEvent(BaseModel):
    """Server-sent event for chat streaming."""

    type: str  # "text", "phase", "action", "complete", "error"
    content: str | None = None
    agent: str | None = None
    tool: str | None = None


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """
    Stream chat responses using Server-Sent Events.

    The ClarifyingAgent will ask questions to build a SearchProfile.
    Events are streamed as they occur:
    - type: "text" - Text content from the agent
    - type: "phase" - Agent handoff occurred
    - type: "action" - Tool was called
    - type: "complete" - Response finished
    - type: "error" - An error occurred
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Get session for conversation persistence
            session = session_manager.get_session(request.session_id)

            # Run agent with streaming
            streaming_result = Runner.run_streamed(
                clarifying_agent,
                input=request.message,
                context={"session": session},
            )

            async for event in streaming_result.stream_events():
                if event.type == "raw_response_event":
                    # Text content from the model
                    if hasattr(event.data, "delta") and event.data.delta:
                        yield f"data: {json.dumps({'type': 'text', 'content': event.data.delta})}\n\n"
                elif event.type == "agent_updated_stream_event":
                    # Agent handoff occurred
                    yield f"data: {json.dumps({'type': 'phase', 'agent': event.new_agent.name})}\n\n"
                elif event.type == "run_item_stream_event":
                    if hasattr(event.item, "type"):
                        if event.item.type == "tool_call_item":
                            tool_name = getattr(event.item, "name", "unknown")
                            yield f"data: {json.dumps({'type': 'action', 'tool': tool_name})}\n\n"
                        elif event.item.type == "tool_call_output_item":
                            # Stream the tool output (event results)
                            output = getattr(event.item, "output", None)
                            if output:
                                yield f"data: {json.dumps({'type': 'events', 'data': output})}\n\n"

            # Signal completion
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.delete("/session/{session_id}")
async def clear_session(session_id: str) -> dict:
    """Clear a conversation session (for 'Reset my tastes' feature)."""
    await session_manager.clear_session(session_id)
    return {"message": "Session cleared", "session_id": session_id}


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}
