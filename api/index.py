"""
FastAPI backend for Calendar Club.

Provides streaming chat endpoint for discovery conversations
using OpenAI Agents SDK.
"""

import json
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

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Check for API key
            if not os.getenv("OPENAI_API_KEY"):
                yield f"data: {json.dumps({'type': 'error', 'content': 'OPENAI_API_KEY not configured'})}\n\n"
                return

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
